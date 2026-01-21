"""WebSocket endpoints for real-time chat."""
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.routing import APIRouter
import json
import logging
import asyncio
import re
from app.core.agent import run_agent
from app.core.prompts import SYSTEM_PROMPT
from app.services.live_service import get_live_service
from app.utils.helpers import generate_session_id
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/ai-agent")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time AI agent interactions.
    
    Message format (Client → Server):
    {
        "type": "text",
        "content": "user message",
        "session_id": "optional session id"
    }
    
    Message format (Server → Client):
    {
        "type": "response",
        "content": "ai response",
        "tool_used": "search",
        "session_id": "session id"
    }
    """
    await websocket.accept()
    session_id = generate_session_id()
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "Connected to AI Agent"
        })
        
        logger.info(f"WebSocket connection established: {session_id}")
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type", "text")
                
                if message_type == "text":
                    query = message.get("content") or message.get("message", "")
                    current_session_id = message.get("session_id") or session_id
                    
                    if not query:
                        await websocket.send_json({
                            "type": "error",
                            "content": "Empty query received"
                        })
                        continue
                    
                    logger.info(f"WebSocket query: {query[:100]}...")
                    
                    # Process query with agent
                    result = await run_agent(query, current_session_id)
                    
                    # Send response
                    await websocket.send_json({
                        "type": "response",
                        "content": result["content"],
                        "tool_used": result["tool_used"],
                        "session_id": result["session_id"],
                        "metadata": result.get("metadata", {})
                    })
                    
                elif message_type == "audio":
                    # Audio handling (for future implementation)
                    await websocket.send_json({
                        "type": "error",
                        "content": "Audio processing not yet implemented"
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Unknown message type: {message_type}"
                    })
                    
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "content": "Invalid JSON format"
                })
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {str(e)}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "content": f"Error processing message: {str(e)}"
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"Connection error: {str(e)}"
            })
        except:
            pass


@router.websocket("/ws/live-chat")
async def live_chat_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for OpenAI Realtime chat with real-time audio support.
    
    This endpoint bridges between the client WebSocket and OpenAI's Realtime API WebSocket,
    enabling real-time bidirectional audio and text streaming.
    
    Message format (Client → Server):
    {
        "type": "text" | "audio" | "setup",
        "content": "text message" (for text)
        "audio": "base64 encoded audio data" (for audio)
        "mime_type": "audio/pcm" (for audio)
        "config": {...} (for setup)
    }
    
    Message format (Server → Client):
    {
        "type": "text" | "audio" | "connected" | "error" | "turn_complete",
        "content": "response text" (for text)
        "audio": "base64 encoded audio" (for audio)
        "mime_type": "audio/..." (for audio)
    }
    """
    await websocket.accept()
    session_id = generate_session_id()
    live_service = None
    openai_ws = None
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "Connected to OpenAI Realtime",
            "features": ["audio", "text"]
        })
        
        logger.info(f"OpenAI Realtime WebSocket connection established: {session_id}")
        
        # Initialize OpenAI Realtime service
        live_service = get_live_service()

        async with live_service.connect() as openai_ws:
            logger.info(f"Realtime session connected for {session_id}")

            # Wait for session.created before updating configuration
            session_ready = False
            while not session_ready:
                raw_msg = await openai_ws.recv()
                data = json.loads(raw_msg)
                if data.get("type") == "session.created":
                    session_ready = True
                elif data.get("type") == "error":
                    raise Exception(f"Realtime session error: {data}")

            # Configure session
            await openai_ws.send(json.dumps({
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": SYSTEM_PROMPT,
                    "voice": settings.OPENAI_REALTIME_VOICE,
                    "input_audio_format": settings.OPENAI_REALTIME_INPUT_FORMAT,
                    "output_audio_format": settings.OPENAI_REALTIME_OUTPUT_FORMAT,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": None
                }
            }))
            
            # Flag to control the receive loop
            receiving = True
            
            def should_skip_navigation(query_text: str) -> bool:
                if not query_text:
                    return False
                text = query_text.lower()
                nav_keywords = [
                    "dashboard",
                    "players",
                    "settings",
                    "chat",
                    "لوحة",
                    "لوحة التحكم",
                    "اللاعبين",
                    "الإعدادات",
                    "الاعدادات",
                    "الدردشة",
                    "المحادثة"
                ]
                if not any(keyword in text for keyword in nav_keywords):
                    return False
                if not any(
                    phrase in text
                    for phrase in ["go to", "open", "take me to", "navigate to", "اذهب", "اذهب إلى", "افتح", "خذني إلى", "انتقل إلى"]
                ):
                    return True
                if any(
                    phrase in text for phrase in [
                        "don't take",
                        "do not take",
                        "don't go",
                        "do not go",
                        "don't navigate",
                        "no navigation",
                        "just explain",
                        "only explain",
                        "without going",
                        "stay here",
                        "don't open",
                        "do not open",
                        "لا تذهب",
                        "لا تروح",
                        "لا تنتقل",
                        "فقط اشرح",
                        "بس اشرح",
                        "بدون ما تروح"
                    ]
                ):
                    return True
                if any(
                    phrase in text for phrase in [
                        "explain",
                        "describe",
                        "tell me about",
                        "what is in",
                        "what's in"
                    ]
                ) and not any(
                    verb in text for verb in ["go to", "take me", "navigate", "open"]
                ):
                    return True
                return False

            async def handle_navigation_intent(query_text: str):
                """Run agent navigation tool and notify client if routing is needed."""
                try:
                    if should_skip_navigation(query_text):
                        return
                    result = await run_agent(query_text, session_id=session_id)
                    target_route = result.get("target_route")
                    if target_route:
                        await websocket.send_json({
                            "type": "navigate",
                            "target_route": target_route,
                            "message": result.get("content", "")
                        })
                except Exception as nav_error:
                    logger.error(f"Navigation check failed: {nav_error}", exc_info=True)
            
            async def receive_from_client():
                """Receive messages from client and send to OpenAI Realtime."""
                nonlocal receiving
                try:
                    while receiving:
                        # Receive message from client
                        data = await websocket.receive_text()
                        
                        try:
                            message = json.loads(data)
                            message_type = message.get("type", "text")
                            
                            if message_type == "text":
                                # Send text to OpenAI Realtime
                                text_content = message.get("content", "")
                                if text_content:
                                    logger.info(f"Sending text to Realtime: {text_content[:50]}...")
                                    response_modalities = message.get("response_modalities") or ["audio", "text"]
                                    asyncio.create_task(handle_navigation_intent(text_content))
                                    await openai_ws.send(json.dumps({
                                        "type": "conversation.item.create",
                                        "item": {
                                            "type": "message",
                                            "role": "user",
                                            "content": [{"type": "input_text", "text": text_content}]
                                        }
                                    }))
                                    await openai_ws.send(json.dumps({
                                        "type": "response.create",
                                        "response": {"modalities": response_modalities}
                                    }))
                            
                            elif message_type == "audio":
                                # Send audio to OpenAI Realtime
                                audio_b64 = message.get("audio", "")
                                mime_type = message.get("mime_type", "audio/pcm")
                                
                                if audio_b64:
                                    try:
                                        logger.info(f"Sending audio chunk to Realtime ({mime_type})")
                                        await openai_ws.send(json.dumps({
                                            "type": "input_audio_buffer.append",
                                            "audio": audio_b64
                                        }))
                                    except Exception as e:
                                        logger.error(f"Error decoding audio: {e}")
                                        await websocket.send_json({
                                            "type": "error",
                                            "content": f"Error processing audio: {str(e)}"
                                        })
                            
                            elif message_type == "audio_stream_end":
                                # Signal end of audio stream to OpenAI Realtime
                                logger.info("Received audioStreamEnd from client, committing buffer")
                                try:
                                    await openai_ws.send(json.dumps({
                                        "type": "input_audio_buffer.commit"
                                    }))
                                    await openai_ws.send(json.dumps({
                                        "type": "response.create",
                                        "response": {"modalities": ["audio", "text"]}
                                    }))
                                    logger.info("Audio buffer committed, response requested")
                                except Exception as e:
                                    logger.error(f"Error sending audio stream end: {e}")
                                    await websocket.send_json({
                                        "type": "error",
                                        "content": f"Error signaling stream end: {str(e)}"
                                    })
                            
                            elif message_type == "tool_response":
                                # Tool responses are not used in Realtime for now
                                logger.info("Tool response received from client (ignored)")
                            
                            else:
                                await websocket.send_json({
                                    "type": "error",
                                    "content": f"Unknown message type: {message_type}"
                                })
                                
                        except json.JSONDecodeError:
                            await websocket.send_json({
                                "type": "error",
                                "content": "Invalid JSON format"
                            })
                        except Exception as e:
                            logger.error(f"Error processing client message: {e}", exc_info=True)
                            await websocket.send_json({
                                "type": "error",
                                "content": f"Error: {str(e)}"
                            })
                except WebSocketDisconnect:
                    logger.info("Client disconnected")
                    receiving = False
                except Exception as e:
                    logger.error(f"Error in receive_from_client: {e}", exc_info=True)
                    receiving = False
            
            async def send_to_client():
                """Receive messages from OpenAI Realtime and send to client."""
                nonlocal receiving
                pending_text = ""
                try:
                    async for raw_message in openai_ws:
                        if not receiving:
                            break

                        try:
                            live_message = json.loads(raw_message)
                        except json.JSONDecodeError:
                            logger.warning("Received non-JSON message from Realtime")
                            continue

                        msg_type = live_message.get("type")

                        # Handle session updated
                        if msg_type == "session.updated":
                            logger.info("Realtime session updated")
                            await websocket.send_json({
                                "type": "setup_complete",
                                "content": "Realtime session ready"
                            })

                        # Text deltas
                        if msg_type in {"response.text.delta", "response.audio_transcript.delta"}:
                            delta = live_message.get("delta", "")
                            pending_text += delta

                        # Final text item
                        if msg_type == "response.output_item.done":
                            item = live_message.get("item", {})
                            content = item.get("content", [])
                            for c in content:
                                if c.get("type") == "text" and c.get("text"):
                                    pending_text = c.get("text")

                        # Audio deltas
                        if msg_type == "response.audio.delta":
                            audio_b64 = live_message.get("delta", "")
                            if audio_b64:
                                await websocket.send_json({
                                    "type": "audio",
                                    "audio": audio_b64,
                                    "mime_type": f"audio/pcm;rate={settings.OPENAI_REALTIME_SAMPLE_RATE}"
                                })

                        # Input audio transcription (STT)
                        if msg_type == "conversation.item.input_audio_transcription.completed":
                            transcript = live_message.get("transcript", "")
                            if transcript:
                                await websocket.send_json({
                                    "type": "transcription",
                                    "content": transcript
                                })
                                asyncio.create_task(handle_navigation_intent(transcript))

                        # Response finished
                        if msg_type == "response.done":
                            if pending_text:
                                await websocket.send_json({
                                    "type": "text",
                                    "content": pending_text
                                })
                                pending_text = ""
                            await websocket.send_json({"type": "turn_complete"})

                        # Errors
                        if msg_type == "error":
                            await websocket.send_json({
                                "type": "error",
                                "content": str(live_message.get("error", live_message))
                            })
                except Exception as e:
                    logger.error(f"Error in send_to_client: {e}", exc_info=True)
                    receiving = False
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "content": f"Realtime API error: {str(e)}"
                        })
                    except:
                        pass
                finally:
                    receiving = False
            
            # Run both tasks concurrently
            await asyncio.gather(
                receive_from_client(),
                send_to_client(),
                return_exceptions=True
            )
        
    except WebSocketDisconnect:
        logger.info(f"OpenAI Realtime WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"OpenAI Realtime WebSocket error: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"Connection error: {str(e)}"
            })
        except:
            pass

