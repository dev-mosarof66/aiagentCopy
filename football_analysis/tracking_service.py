import logging
import os
import shutil
import subprocess
import cv2
import numpy as np
import PIL.Image
from pathlib import Path
from norfair import Tracker, Video
from norfair.camera_motion import MotionEstimator
from norfair.distances import mean_euclidean

from .inference import Converter, HSVClassifier, InertiaClassifier, YoloV5
from .run_utils import (
    get_ball_detections,
    get_main_ball,
    get_player_detections,
    update_motion_estimator,
)
from .soccer import Match, Player, Team
from .soccer.pass_event import Pass
from .auto_calibrate import auto_calibrate
from .tactical_view import TacticalViewProjector
from .court_keypoint_detector import CourtKeypointDetector

logger = logging.getLogger(__name__)

class TrackingService:
    def __init__(self, model_path="models/ball.pt", keypoint_model_path="models/keypoint_detector.pt"):
        # Resolve paths relative to this file
        base_path = Path(__file__).parent
        self.model_path = str(base_path / model_path)
        self.keypoint_model_path = str(base_path / keypoint_model_path)
        
        # Initialize detectors
        self.player_detector = YoloV5()
        self.ball_detector = YoloV5(model_path=self.model_path)
        self.court_detector = CourtKeypointDetector(model_path=self.keypoint_model_path)

    def build_match_setup(self, match_key, fps, pixels_to_meters=None):
        if match_key == "chelsea_man_city":
            home = Team(name="Chelsea", abbreviation="CHE", color=(255, 0, 0), board_color=(244, 86, 64), text_color=(255, 255, 255))
            away = Team(name="Man City", abbreviation="MNC", color=(240, 230, 188), text_color=(0, 0, 0))
            initial_possession = away
        elif match_key == "real_madrid_barcelona":
            home = Team(name="Real Madrid", abbreviation="RMA", color=(255, 255, 255), board_color=(235, 214, 120), text_color=(0, 0, 0))
            away = Team(name="Barcelona", abbreviation="BAR", color=(128, 0, 128), board_color=(28, 43, 92), text_color=(255, 215, 0))
            initial_possession = home
        elif match_key == "france_croatia":
            home = Team(name="France", abbreviation="FRA", color=(0, 56, 168), board_color=(16, 44, 87), text_color=(255, 255, 255))
            away = Team(name="Croatia", abbreviation="CRO", color=(208, 16, 44), board_color=(230, 230, 230), text_color=(0, 0, 0))
            initial_possession = home
        else:
            # Default or generic setup
            home = Team(name="Home", abbreviation="HOM", color=(255, 255, 255))
            away = Team(name="Away", abbreviation="AWY", color=(0, 0, 0))
            initial_possession = home

        match = Match(home=home, away=away, fps=fps, pixels_to_meters=pixels_to_meters)
        match.team_possession = initial_possession
        return match, [home, away]

    async def process_video(self, video_path: str, match_key: str = "chelsea_man_city", output_video_path: str = None):
        """
        Process a video and return tracking data in JSON-serializable format.
        If output_video_path is provided, writes the annotated video to that path.
        """
        video = Video(input_path=video_path)
        fps = video.video_capture.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(video.video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(video.video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Auto-calibrate pixels_to_meters
        pixels_to_meters = auto_calibrate(video_path, verbose=False)
        
        match, teams = self.build_match_setup(match_key=match_key, fps=fps, pixels_to_meters=pixels_to_meters)
        
        from .inference.filters import get_filters_for_match
        filters_for_match = get_filters_for_match(match_key)
        hsv_classifier = HSVClassifier(filters=filters_for_match)
        classifier = InertiaClassifier(classifier=hsv_classifier, inertia=20)
        
        player_tracker = Tracker(distance_function=mean_euclidean, distance_threshold=250, initialization_delay=3, hit_counter_max=90)
        ball_tracker = Tracker(distance_function=mean_euclidean, distance_threshold=150, initialization_delay=20, hit_counter_max=2000)
        motion_estimator = MotionEstimator()
        tactical_projector = TacticalViewProjector(pixels_to_meters=pixels_to_meters)
        
        # Initialize VideoWriter if output path provided
        video_writer = None
        temp_output_path = None
        if output_video_path:
            # We use a temporary file for the initial OpenCV write
            # because we need to remux it with ffmpeg later to ensure web compatibility
            temp_output_path = output_video_path + ".tmp.mp4"
            fourcc = cv2.VideoWriter_fourcc(*'mp4v') # mp4v is reliable for writing
            video_writer = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))

        results = {
            "metadata": {
                "fps": fps,
                "match_key": match_key,
                "pixels_to_meters": pixels_to_meters,
                "home": {
                    "name": match.home.name,
                    "abbr": match.home.abbreviation,
                    "color": match.home.color
                },
                "away": {
                    "name": match.away.name,
                    "abbr": match.away.abbreviation,
                    "color": match.away.color
                }
            },
            "frames": []
        }
        
        import asyncio
        for i, frame in enumerate(video):
            if i % 10 == 0:
                await asyncio.sleep(0.01) # Yield to event loop to prevent websocket timeout
            
            if i == 0:
                match.reset_distance_tracking()

            # Detections
            players_det = get_player_detections(self.player_detector, frame)
            ball_det = get_ball_detections(self.ball_detector, frame)
            
            # Detect court keypoints
            court_keypoints = self.court_detector.get_court_keypoints([frame])
            if court_keypoints:
                tactical_projector.update_homography_from_keypoints(court_keypoints[0])

            # Update trackers
            coord_transformations = update_motion_estimator(motion_estimator=motion_estimator, detections=players_det + ball_det, frame=frame)
            
            player_track_objects = player_tracker.update(detections=players_det, coord_transformations=coord_transformations)
            ball_track_objects = ball_tracker.update(detections=ball_det, coord_transformations=coord_transformations)
            
            player_detections = Converter.TrackedObjects_to_Detections(player_track_objects)
            ball_detections = Converter.TrackedObjects_to_Detections(ball_track_objects)
            
            player_detections = classifier.predict_from_detections(detections=player_detections, img=frame)
            
            ball = get_main_ball(ball_detections)
            players = Player.from_detections(detections=player_detections, teams=teams)
            match.update(players, ball, frame=frame)

            # Draw annotations for output video
            if video_writer:
                pil_frame = PIL.Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                pil_frame = Player.draw_players(players, pil_frame, id=True, match=match)
                if ball:
                    pil_frame = ball.draw(pil_frame)
                
                # Convert back and write
                annotated_frame = cv2.cvtColor(np.array(pil_frame), cv2.COLOR_RGB2BGR)
                video_writer.write(annotated_frame)

            tactical_positions = {}
            if tactical_projector.try_initialize(frame) and tactical_projector.ready:
                projections = tactical_projector.project_players(players)
                for proj in projections:
                    if proj.player_id is not None and proj.position is not None:
                        tactical_positions[proj.player_id] = [float(proj.position[0]), float(proj.position[1])]
            
            # Prepare frame data
            frame_data = {
                "frame_index": i,
                "players": [],
                "ball": None,
                "possession": {
                    "team": match.team_possession.name if match.team_possession else None,
                    "player_id": match.closest_player.player_id if match.closest_player else None,
                    "home_time": match.home.get_time_possession(match.fps),
                    "away_time": match.away.get_time_possession(match.fps),
                    "home_pct": int(match.home.get_percentage_possession(match.duration) * 100),
                    "away_pct": int(match.away.get_percentage_possession(match.duration) * 100)
                },
                "tactical_positions": tactical_positions
            }
            
            for p in players:
                frame_data["players"].append({
                    "id": p.player_id,
                    "team": p.team.name if p.team else "unknown",
                    "position": [float(val) for val in p.detection.points[0]] if p.detection else None
                })
            
            if ball and ball.detection:
                frame_data["ball"] = {
                    "position": [float(val) for val in ball.detection.points[0]]
                }
                
            results["frames"].append(frame_data)
            
            # Optional: limit frames for performance if needed, but making it much larger
            if i > 5000: 
                break
        
        if video_writer:
            video_writer.release()
            # Remux with ffmpeg to ensure H.264 + faststart for web playback
            if temp_output_path and os.path.exists(temp_output_path):
                try:
                    # -c:v libx264 ensures H.264
                    # -pix_fmt yuv420p is required for many players
                    # -movflags +faststart moves MooV atom to start for streaming
                    cmd = [
                        'ffmpeg', '-i', temp_output_path,
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart', '-y', output_video_path
                    ]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    # Cleanup temp file
                    os.remove(temp_output_path)
                except Exception as e:
                    logger.error(f"Ffmpeg remuxing failed: {e}")
                    # Fallback: just move the temp file to original if ffmpeg failed
                    shutil.move(temp_output_path, output_video_path)
                
        return results
