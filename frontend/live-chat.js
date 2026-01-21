// Configuration
const WS_URL = window.location.origin.replace('http://', 'ws://').replace('https://', 'wss://');
const LIVE_API_WS_URL = `${WS_URL}/ws/live-chat`;

// DOM Elements
const recordButton = document.getElementById('recordButton');
const recordIcon = document.getElementById('recordIcon');
const statusMessage = document.getElementById('statusMessage');
const messagesContainer = document.getElementById('messagesContainer');
const visualizer = document.getElementById('visualizer');
const connectionDot = document.getElementById('connectionDot');
const connectionText = document.getElementById('connectionText');
const audioModeBtn = document.getElementById('audioModeBtn');
const textModeBtn = document.getElementById('textModeBtn');
const textInputSection = document.getElementById('textInputSection');
const textInput = document.getElementById('textInput');
const sendTextBtn = document.getElementById('sendTextBtn');

// State
let websocket = null;
let isRecording = false;
let mediaRecorder = null;
let audioContext = null;
let analyser = null;
let microphone = null;
let visualizerInterval = null;
let currentMode = 'audio'; // 'audio' or 'text'
let audioChunks = [];

// Audio playback queue
let audioQueue = [];
let isPlayingAudio = false;
let hasShownAudioIndicator = false;
let pendingAudioChunks = [];
let pendingAudioMimeType = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeVisualizer();
    connectToLiveAPI();
    
    // Event listeners
    recordButton.addEventListener('click', toggleRecording);
    audioModeBtn.addEventListener('click', () => switchMode('audio'));
    textModeBtn.addEventListener('click', () => switchMode('text'));
    sendTextBtn.addEventListener('click', sendTextMessage);
    textInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendTextMessage();
    });
});

// Mode switching
function switchMode(mode) {
    currentMode = mode;
    
    if (mode === 'audio') {
        audioModeBtn.classList.add('active');
        textModeBtn.classList.remove('active');
        textInputSection.style.display = 'none';
        recordButton.style.display = 'flex';
        visualizer.style.display = 'flex';
        statusMessage.textContent = 'Click to start recording';
    } else {
        textModeBtn.classList.add('active');
        audioModeBtn.classList.remove('active');
        textInputSection.style.display = 'flex';
        recordButton.style.display = 'none';
        visualizer.style.display = 'none';
        statusMessage.textContent = 'Type your message below';
    }
}

// Initialize visualizer
function initializeVisualizer() {
    for (let i = 0; i < 32; i++) {
        const bar = document.createElement('div');
        bar.className = 'visualizer-bar';
        bar.style.height = '20px';
        visualizer.appendChild(bar);
    }
}

// Connect to OpenAI Realtime WebSocket
function connectToLiveAPI() {
    updateConnectionStatus('connecting', 'Connecting...');
    
    try {
        websocket = new WebSocket(LIVE_API_WS_URL);
        
        websocket.onopen = () => {
            console.log('Connected to OpenAI Realtime');
            updateConnectionStatus('connected', 'Connected');
            statusMessage.textContent = 'Ready! Click to start recording';
        };
        
        websocket.onmessage = (event) => {
            handleServerMessage(JSON.parse(event.data));
        };
        
        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            updateConnectionStatus('disconnected', 'Error');
            statusMessage.textContent = 'Connection error';
        };
        
        websocket.onclose = () => {
            console.log('Disconnected from OpenAI Realtime');
            updateConnectionStatus('disconnected', 'Disconnected');
            statusMessage.textContent = 'Disconnected. Reconnecting...';
            
            // Reconnect after 3 seconds
            setTimeout(connectToLiveAPI, 3000);
        };
    } catch (error) {
        console.error('Failed to connect:', error);
        updateConnectionStatus('disconnected', 'Failed');
    }
}

// Handle server messages
function handleServerMessage(message) {
    console.log('Received message:', message);
    
    switch (message.type) {
        case 'connected':
            console.log('Session connected:', message.session_id);
            addSystemMessage('Connected to OpenAI Realtime');
            break;
        
        case 'setup_complete':
            console.log('Setup complete');
            break;
        
        case 'text':
            addMessage(message.content, 'bot');
            break;
        
        case 'audio':
            bufferAudioChunk(message.audio, message.mime_type);
            break;
        
        case 'turn_complete':
            console.log('Turn complete');
            statusMessage.textContent = 'Response complete';
            finalizeAudioResponse();
            break;
        
        case 'error':
            addSystemMessage(`Error: ${message.content}`, true);
            break;
        
        case 'tool_call':
            addSystemMessage('Using tools...');
            break;
        
        case 'transcription':
            addMessage(message.content, 'user');
            break;
        
        default:
            console.log('Unknown message type:', message.type);
    }
}

// Toggle recording
async function toggleRecording() {
    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

// Start recording
async function startRecording() {
    try {
        // Request microphone access with specific PCM settings
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                sampleRate: 16000,  // 16kHz PCM input for OpenAI Realtime
                channelCount: 1,     // Mono
                echoCancellation: true,
                noiseSuppression: true
            } 
        });
        
        // Set up audio context for visualization AND PCM extraction
        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000
        });
        analyser = audioContext.createAnalyser();
        microphone = audioContext.createMediaStreamSource(stream);
        microphone.connect(analyser);
        analyser.fftSize = 64;
        
        // Start visualizer
        startVisualizer();
        
        // Create ScriptProcessor to extract PCM data
        const bufferSize = 4096;
        const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);
        
        microphone.connect(processor);
        processor.connect(audioContext.destination);
        
        processor.onaudioprocess = (e) => {
            if (!isRecording) return;
            
            // Get PCM data (Float32Array)
            const inputData = e.inputBuffer.getChannelData(0);
            
            // Convert Float32 to Int16 PCM
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                // Clamp values to [-1, 1] and convert to 16-bit
                const s = Math.max(-1, Math.min(1, inputData[i]));
                pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            
            // Convert to base64
            const base64Audio = btoa(
                String.fromCharCode.apply(null, new Uint8Array(pcmData.buffer))
            );
            
            // Send PCM audio to server
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({
                    type: 'audio',
                    audio: base64Audio,
                    mime_type: 'audio/pcm;rate=16000'
                }));
            }
        };
        
        // Store processor for cleanup
        mediaRecorder = { processor, stream };
        
        isRecording = true;
        recordButton.classList.add('recording');
        recordIcon.textContent = '⏸️';
        statusMessage.textContent = 'Recording... Click to stop';
        
        // Reset audio indicator flag for new recording
        hasShownAudioIndicator = false;
        
        console.log('Recording started (PCM mode)');
        
    } catch (error) {
        console.error('Error starting recording:', error);
        statusMessage.textContent = 'Failed to access microphone';
        alert('Could not access microphone. Please check permissions.');
    }
}

// Stop recording
function stopRecording() {
    isRecording = false;
    
    if (mediaRecorder) {
        // Stop processor if it exists
        if (mediaRecorder.processor) {
            mediaRecorder.processor.disconnect();
        }
        
        // Stop all tracks
        if (mediaRecorder.stream) {
            mediaRecorder.stream.getTracks().forEach(track => track.stop());
        }
    }
    
    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }
    
    // IMPORTANT: Signal to OpenAI Realtime that audio stream has ended
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        console.log('Sending audioStreamEnd signal to OpenAI Realtime');
        websocket.send(JSON.stringify({
            type: 'audio_stream_end'
        }));
    }
    
    stopVisualizer();
    
    recordButton.classList.remove('recording');
    recordIcon.textContent = '🎤';
    statusMessage.textContent = 'Processing...';
    
    console.log('Recording stopped, waiting for response');
}

// Start visualizer animation
function startVisualizer() {
    const bars = visualizer.querySelectorAll('.visualizer-bar');
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    
    function updateVisualizer() {
        if (!isRecording) return;
        
        analyser.getByteFrequencyData(dataArray);
        
        bars.forEach((bar, i) => {
            const value = dataArray[i] || 0;
            const height = Math.max(20, (value / 255) * 80);
            bar.style.height = `${height}px`;
        });
        
        requestAnimationFrame(updateVisualizer);
    }
    
    updateVisualizer();
}

// Stop visualizer
function stopVisualizer() {
    const bars = visualizer.querySelectorAll('.visualizer-bar');
    bars.forEach(bar => {
        bar.style.height = '20px';
    });
}

// Buffer audio response chunks from server
function bufferAudioChunk(base64Audio, mimeType) {
    try {
        if (!base64Audio) return;

        const binaryString = atob(base64Audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        if (bytes.length === 0) {
            console.log('Empty audio data received, skipping');
            return;
        }

        pendingAudioChunks.push(bytes);
        pendingAudioMimeType = mimeType || pendingAudioMimeType || 'audio/pcm;rate=24000';

    } catch (error) {
        console.error('Error handling audio response:', error);
        addSystemMessage('Error playing audio response', true);
    }
}

// Finalize buffered audio into a single WAV and enqueue playback
function finalizeAudioResponse() {
    if (!pendingAudioChunks.length) {
        return;
    }

    const pcmBytes = concatUint8Arrays(pendingAudioChunks);
    const sampleRate = getSampleRateFromMime(pendingAudioMimeType) || 24000;
    const wavBlob = createWavBlob(pcmBytes, sampleRate);
    const audioUrl = URL.createObjectURL(wavBlob);

    audioQueue.push(audioUrl);
    pendingAudioChunks = [];
    pendingAudioMimeType = null;

    if (!hasShownAudioIndicator) {
        addSystemMessage('🔊 Playing audio response...');
        hasShownAudioIndicator = true;
    }

    if (!isPlayingAudio) {
        playNextAudio();
    }
}

function concatUint8Arrays(chunks) {
    const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const result = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {
        result.set(chunk, offset);
        offset += chunk.length;
    }
    return result;
}

function getSampleRateFromMime(mimeType) {
    if (!mimeType) return null;
    const match = /rate=(\d+)/.exec(mimeType);
    return match ? parseInt(match[1], 10) : null;
}

function createWavBlob(pcmBytes, sampleRate) {
    const numChannels = 1;
    const bitsPerSample = 16;
    const blockAlign = numChannels * bitsPerSample / 8;
    const byteRate = sampleRate * blockAlign;
    const dataSize = pcmBytes.length;

    const buffer = new ArrayBuffer(44);
    const view = new DataView(buffer);

    // RIFF header
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeString(view, 8, 'WAVE');
    // fmt subchunk
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true); // PCM
    view.setUint16(20, 1, true);  // audio format
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    // data subchunk
    writeString(view, 36, 'data');
    view.setUint32(40, dataSize, true);

    const wavBytes = new Uint8Array(44 + dataSize);
    wavBytes.set(new Uint8Array(buffer), 0);
    wavBytes.set(pcmBytes, 44);

    return new Blob([wavBytes], { type: 'audio/wav' });
}

function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

// Play next audio in queue (auto-play from speakers)
function playNextAudio() {
    if (audioQueue.length === 0) {
        isPlayingAudio = false;
        hasShownAudioIndicator = false; // Reset for next response
        statusMessage.textContent = 'Ready! Click to start recording';
        return;
    }
    
    isPlayingAudio = true;
    const audioUrl = audioQueue.shift();
    
    // Create invisible audio element that auto-plays
    const audio = new Audio(audioUrl);
    audio.autoplay = true;
    
    audio.onended = () => {
        console.log('Audio playback finished');
        URL.revokeObjectURL(audioUrl);
        playNextAudio();
    };
    
    audio.onerror = (error) => {
        console.error('Error playing audio:', error);
        URL.revokeObjectURL(audioUrl);
        playNextAudio();
    };
    
    audio.onloadedmetadata = () => {
        console.log(`Audio duration: ${audio.duration}s`);
        if (audio.duration === 0 || isNaN(audio.duration)) {
            console.warn('Invalid audio duration, skipping');
            URL.revokeObjectURL(audioUrl);
            playNextAudio();
        }
    };
    
    statusMessage.textContent = '🔊 Playing response...';
    
    // Start playing (browsers may require user interaction first)
    audio.play().catch(err => {
        console.error('Autoplay failed:', err);
        addSystemMessage('Click anywhere to enable audio playback');
    });
}

// Send text message
function sendTextMessage() {
    const message = textInput.value.trim();
    if (!message || !websocket || websocket.readyState !== WebSocket.OPEN) {
        return;
    }
    
    // Add user message to chat
    addMessage(message, 'user');
    
    // Send to server
    websocket.send(JSON.stringify({
        type: 'text',
        content: message,
        response_modalities: currentMode === 'text' ? ['text'] : ['audio', 'text']
    }));
    
    // Clear input
    textInput.value = '';
    statusMessage.textContent = 'Waiting for response...';
}

// Add text message to chat
function addMessage(text, type) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `live-message ${type}`;
    messageDiv.textContent = text;
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Add audio message to chat
function addAudioMessage(audioUrl) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'live-message bot audio';
    
    const text = document.createElement('div');
    text.textContent = '🔊 Audio Response';
    messageDiv.appendChild(text);
    
    const audioPlayerContainer = document.createElement('div');
    audioPlayerContainer.className = 'audio-player-container';
    
    const audio = document.createElement('audio');
    audio.controls = true;
    audio.src = audioUrl;
    audioPlayerContainer.appendChild(audio);
    
    messageDiv.appendChild(audioPlayerContainer);
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Add system message
function addSystemMessage(text, isError = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'live-message';
    messageDiv.style.background = isError ? '#ffebee' : '#e8f5e9';
    messageDiv.style.borderLeft = `4px solid ${isError ? '#f44336' : '#4caf50'}`;
    messageDiv.style.marginLeft = '10%';
    messageDiv.style.marginRight = '10%';
    messageDiv.style.fontSize = '12px';
    messageDiv.style.color = '#666';
    messageDiv.textContent = text;
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Update connection status
function updateConnectionStatus(status, text) {
    connectionDot.className = `connection-dot ${status}`;
    connectionText.textContent = text;
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    if (websocket) {
        websocket.close();
    }
    if (isRecording) {
        stopRecording();
    }
});

