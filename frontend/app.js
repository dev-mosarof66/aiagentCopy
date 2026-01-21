// API Configuration
const API_BASE_URL = window.location.origin;
const WS_URL = API_BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://');
const LIVE_API_WS_URL = `${WS_URL}/ws/live-chat`;

// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const micButton = document.getElementById('micButton');
const fileInput = document.getElementById('fileInput');
const uploadButton = document.getElementById('uploadButton');
const uploadStatus = document.getElementById('uploadStatus');
const connectionStatus = document.getElementById('connectionStatus');

// UI Elements
const chatToggleButton = document.getElementById('chatToggleButton');
const chatPopup = document.getElementById('chatPopup');
const closeChatButton = document.getElementById('closeChatButton');
const navMicButton = document.getElementById('navMicButton');
const navItems = document.querySelectorAll('.nav-item');
const pageTitle = document.getElementById('pageTitle');
const pageContent = document.getElementById('pageContent');

// State
let sessionId = null;
let isProcessing = false;
let isRecording = false;

// Live audio state
let liveWebSocket = null;
let audioContext = null;
let mediaRecorder = null;
let pendingAudioChunks = [];
let pendingAudioMimeType = null;
let audioQueue = [];
let isPlayingAudio = false;
let hasShownAudioIndicator = false;
let activeRecordingTarget = null;
let activeRecordingMode = null;
let navAwaitingResponse = false;
let lastResponseText = null;
let navResponseTimeout = null;
let navSuppressRealtime = false;
let awaitingRealtimeResponse = false;
let activeAudio = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Chat UI Events
    chatToggleButton.addEventListener('click', toggleChat);
    closeChatButton.addEventListener('click', toggleChat);

    // Message Events
    messageInput.addEventListener('keypress', handleKeyPress);
    sendButton.addEventListener('click', handleSendMessage);

    // File upload handlers
    if (uploadButton) {
        uploadButton.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', handleFileUpload);
    }

    // Sidebar Navigation
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.getAttribute('data-page');
            navigateTo(page);
        });
    });

    // Live audio (OpenAI Realtime)
    connectToLiveAPI();
    micButton.addEventListener('click', () => toggleRecording('chat', micButton));
    if (navMicButton) {
        navMicButton.addEventListener('click', () => toggleRecording('nav', navMicButton));
    }

    // Load initial page
    const initialPage = window.location.hash.substring(1) || 'dashboard';
    navigateTo(initialPage);
});

// Navigation logic
function navigateTo(page) {
    // Update Active State
    navItems.forEach(item => {
        if (item.getAttribute('data-page') === page) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Update Title and Hash
    pageTitle.textContent = page.charAt(0).toUpperCase() + page.slice(1);
    window.location.hash = page;

    // Load Dummy Content
    renderPage(page);
}

function renderPage(page) {
    console.log('Rendering page:', page);
    const normalizedPage = (page || '').toString().trim().toLowerCase();

    // If the page is 'chat', show the chat popup instead of dummy content
    if (normalizedPage === 'chat') {
        pageContent.innerHTML = '';
        pageContent.style.padding = '0';
        pageContent.style.overflow = 'hidden';

        // Move the chat popup into the main content area and adjust styling
        chatPopup.classList.remove('hidden');
        chatPopup.style.position = 'static';
        chatPopup.style.bottom = 'auto';
        chatPopup.style.right = 'auto';
        chatPopup.style.width = '100%';
        chatPopup.style.height = '100%';
        chatPopup.style.maxHeight = 'none';
        chatPopup.style.borderRadius = '0';
        chatPopup.style.boxShadow = 'none';
        chatPopup.style.zIndex = 'auto';
        chatPopup.style.border = 'none';
        pageContent.appendChild(chatPopup);

        if (closeChatButton) closeChatButton.style.display = 'none';
        messageInput.focus();
    } else if (normalizedPage === 'football') {
        renderFootballPage();
    } else {
        // For other pages, hide the chat and show dummy content
        pageContent.style.padding = '32px';
        pageContent.style.overflow = 'auto';

        if (closeChatButton) closeChatButton.style.display = 'block';

        if (chatPopup.parentElement === pageContent) {
            document.body.appendChild(chatPopup);
        }
        chatPopup.classList.add('hidden');
        chatPopup.style.position = 'fixed';
        chatPopup.style.bottom = '100px';
        chatPopup.style.right = '30px';
        chatPopup.style.width = '450px';
        chatPopup.style.height = '600px';
        chatPopup.style.maxHeight = '600px';
        chatPopup.style.borderRadius = '16px';
        chatPopup.style.boxShadow = '0 12px 48px rgba(0, 0, 0, 0.15)';
        chatPopup.style.zIndex = '1000';
        chatPopup.style.border = '1px solid var(--border-color)';

        let content = `<div class="dummy-card"><h3>${page.charAt(0).toUpperCase() + page.slice(1)}</h3><p>This is a placeholder for the ${page} page.</p></div>`;
        pageContent.innerHTML = content;
    }
}

// Chat UI logic
function toggleChat() {
    chatPopup.classList.toggle('hidden');
    if (!chatPopup.classList.contains('hidden')) {
        messageInput.focus();
    }
}

// Handle file upload
async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    uploadStatus.textContent = `Uploading ${file.name}...`;
    uploadStatus.className = 'upload-status';
    uploadButton.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/api/ai-agent/upload`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            uploadStatus.textContent = `✓ ${file.name} ingested!`;
            uploadStatus.className = 'upload-status success';
            addMessage(`I've processed the file "${file.name}". You can now ask me questions about its content!`, 'bot');
        } else {
            throw new Error(data.detail || 'Upload failed');
        }
    } catch (error) {
        console.error('Upload error:', error);
        uploadStatus.textContent = `✗ Error: ${error.message}`;
        uploadStatus.className = 'upload-status error';
    } finally {
        uploadButton.disabled = false;
        fileInput.value = ''; // Reset for same file re-upload
    }
}

// Connect to Live API WebSocket
function connectToLiveAPI() {
    updateConnectionStatus('connecting', 'Connecting...');

    try {
        liveWebSocket = new WebSocket(LIVE_API_WS_URL);

        liveWebSocket.onopen = () => {
            updateConnectionStatus('connected', 'Ready');
        };

        liveWebSocket.onmessage = (event) => {
            handleLiveMessage(JSON.parse(event.data));
        };

        liveWebSocket.onerror = (error) => {
            console.error('Live WebSocket error:', error);
            updateConnectionStatus('disconnected', 'Error');
        };

        liveWebSocket.onclose = () => {
            updateConnectionStatus('disconnected', 'Disconnected');
            setTimeout(connectToLiveAPI, 3000);
        };
    } catch (error) {
        console.error('Failed to connect to Live API:', error);
        updateConnectionStatus('disconnected', 'Failed');
    }
}

function handleLiveMessage(message) {
    switch (message.type) {
        case 'connected':
            addMessage('Connected to OpenAI Realtime', 'bot');
            break;
        case 'text':
            if (navSuppressRealtime && navAwaitingResponse) {
                return;
            }
            if (!isNavigationPayload(message.content)) {
                addMessage(message.content, 'bot');
                lastResponseText = message.content;
                scheduleNavSpeechFallback();
            }
            setNavResponding(true);
            break;
        case 'audio':
            if (navSuppressRealtime && navAwaitingResponse) {
                clearNavSpeechFallback();
                return;
            }
            if (!awaitingRealtimeResponse) {
                return;
            }
            clearNavSpeechFallback();
            bufferAudioChunk(message.audio, message.mime_type);
            setNavResponding(true);
            break;
        case 'transcription':
            addMessage(message.content, 'user');
            handleNavAssist(message.content);
            break;
        case 'navigate':
            if (message.message) {
                addMessage(message.message, 'bot', 'navigation');
                lastResponseText = message.message;
                scheduleNavSpeechFallback();
            }
            if (message.target_route) {
                const page = message.target_route.replace('#', '');
                navigateTo(page);
            }
            setNavResponding(false);
            break;
        case 'turn_complete':
            clearNavSpeechFallback();
            if (navSuppressRealtime) {
                pendingAudioChunks = [];
                navSuppressRealtime = false;
                lastResponseText = null;
                navAwaitingResponse = false;
                awaitingRealtimeResponse = false;
                setNavResponding(false);
                break;
            }
            if (pendingAudioChunks.length) {
                finalizeAudioResponse();
            } else if (navAwaitingResponse && lastResponseText) {
                speakTextResponse(lastResponseText);
            }
            lastResponseText = null;
            navAwaitingResponse = false;
            awaitingRealtimeResponse = false;
            setNavResponding(false);
            break;
        case 'error':
            addMessage(`Error: ${message.content}`, 'bot', null, true);
            break;
        default:
            break;
    }
}

function toggleRecording(mode, buttonEl) {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording(mode, buttonEl);
    }
}

async function startRecording(mode, buttonEl) {
    try {
        if (isRecording) return;
        resetNavAssistState();
        resetAudioPlaybackState();
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true
            }
        });

        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000
        });

        const microphone = audioContext.createMediaStreamSource(stream);
        const bufferSize = 4096;
        const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);

        microphone.connect(processor);
        processor.connect(audioContext.destination);

        processor.onaudioprocess = (e) => {
            if (!isRecording || !liveWebSocket || liveWebSocket.readyState !== WebSocket.OPEN) return;

            const inputData = e.inputBuffer.getChannelData(0);
            const pcmData = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                const s = Math.max(-1, Math.min(1, inputData[i]));
                pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            const base64Audio = btoa(
                String.fromCharCode.apply(null, new Uint8Array(pcmData.buffer))
            );

            liveWebSocket.send(JSON.stringify({
                type: 'audio',
                audio: base64Audio,
                mime_type: 'audio/pcm;rate=16000'
            }));
        };

        mediaRecorder = { processor, stream };
        isRecording = true;
        activeRecordingMode = mode;
        activeRecordingTarget = buttonEl;
        if (activeRecordingTarget) {
            activeRecordingTarget.classList.add('recording');
        }
        navAwaitingResponse = false;
        awaitingRealtimeResponse = false;
        setNavResponding(false);
        updateConnectionStatus('recording', 'Listening...');
        hasShownAudioIndicator = false;
    } catch (error) {
        console.error('Error starting recording:', error);
        addMessage('Could not access microphone. Please check permissions.', 'bot', null, true);
    }
}

function stopRecording() {
    isRecording = false;

    if (mediaRecorder) {
        if (mediaRecorder.processor) {
            mediaRecorder.processor.disconnect();
        }
        if (mediaRecorder.stream) {
            mediaRecorder.stream.getTracks().forEach(track => track.stop());
        }
    }

    if (audioContext) {
        audioContext.close();
        audioContext = null;
    }

    if (liveWebSocket && liveWebSocket.readyState === WebSocket.OPEN) {
        liveWebSocket.send(JSON.stringify({ type: 'audio_stream_end' }));
    }

    if (activeRecordingTarget) {
        activeRecordingTarget.classList.remove('recording');
    }
    if (activeRecordingMode === 'nav') {
        navAwaitingResponse = true;
    }
    awaitingRealtimeResponse = true;
    activeRecordingMode = null;
    activeRecordingTarget = null;
    updateConnectionStatus('connected', 'Processing...');
}

function scheduleNavSpeechFallback() {
    if (!navAwaitingResponse || !lastResponseText || navSuppressRealtime) return;
    clearNavSpeechFallback();
    navResponseTimeout = setTimeout(() => {
        if (navAwaitingResponse && !pendingAudioChunks.length && lastResponseText) {
            speakTextResponse(lastResponseText);
            lastResponseText = null;
            navAwaitingResponse = false;
        }
    }, 2500);
}

function clearNavSpeechFallback() {
    if (navResponseTimeout) {
        clearTimeout(navResponseTimeout);
        navResponseTimeout = null;
    }
}

function resetNavAssistState() {
    navSuppressRealtime = false;
    clearNavSpeechFallback();
}

function resetAudioPlaybackState() {
    pendingAudioChunks = [];
    pendingAudioMimeType = null;
    audioQueue = [];
    isPlayingAudio = false;
    hasShownAudioIndicator = false;
    if (activeAudio) {
        try {
            activeAudio.pause();
        } catch (error) {
            console.warn('Failed to pause active audio', error);
        }
        activeAudio = null;
    }
}

async function handleNavAssist(transcript) {
    if (!navAwaitingResponse || !transcript) return;
    try {
        const response = await fetch(`${API_BASE_URL}/api/ai-agent/assist`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                command: transcript,
                context: { current_page: window.location.hash || '#dashboard' }
            })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || 'Assist failed');
        }

        if (data.message) {
            addMessage(data.message, 'bot', 'navigation');
            lastResponseText = data.message;
        }

        if (Array.isArray(data.actions)) {
            executeAssistActions(data.actions);
        }

        if (data.handled) {
            navSuppressRealtime = true;
            clearNavSpeechFallback();
            if (lastResponseText) {
                speakTextResponse(lastResponseText);
            }
            lastResponseText = null;
            navAwaitingResponse = false;
            awaitingRealtimeResponse = false;
        }
    } catch (error) {
        console.error('Nav assist error:', error);
    }
}

function executeAssistActions(actions) {
    actions.forEach(action => {
        if (!action || !action.type) return;
        switch (action.type) {
            case 'navigate': {
                const target = (action.value || '').replace('#', '');
                if (target) navigateTo(target);
                break;
            }
            case 'open_chat':
                openChatView();
                break;
            case 'open_upload':
                if (uploadButton) uploadButton.click();
                break;
            case 'focus_chat_input':
                if (messageInput) messageInput.focus();
                break;
            case 'insert_text':
                if (messageInput && typeof action.value === 'string') {
                    messageInput.value = action.value;
                    messageInput.focus();
                }
                break;
            case 'send_text':
                if (messageInput) {
                    handleSendMessage();
                }
                break;
            case 'show_guide':
                showNavGuide();
                break;
            case 'highlight':
                if (action.target) highlightElement(action.target);
                break;
            default:
                break;
        }
    });
}

function openChatView() {
    if (window.location.hash !== '#chat') {
        navigateTo('chat');
    }
    if (chatPopup.classList.contains('hidden')) {
        chatPopup.classList.remove('hidden');
    }
}

function showNavGuide() {
    const guide = [
        'Here is a quick guide to the site:',
        '• Use Chat to ask questions or learn from uploaded files.',
        '• Click Upload in Chat to add Excel, text, or PDF files.',
        '• Ask: "Summarize the academy rules" or "Show me player stats."',
        '• Use the sidebar to open Dashboard, Players, Stats, or Settings.',
        '• Say: "Upload a file", "Open chat", or "Type my question".'
    ].join('\n');
    addMessage(guide, 'bot', 'navigation');
}

function highlightElement(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.classList.add('assist-highlight');
    setTimeout(() => {
        el.classList.remove('assist-highlight');
    }, 2000);
}

function setNavResponding(isResponding) {
    if (!navMicButton) return;
    if (isResponding && navAwaitingResponse) {
        navMicButton.classList.add('responding');
    } else {
        navMicButton.classList.remove('responding');
    }
}

// Handle Enter key
function handleKeyPress(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
    }
}

// Handle send message
async function handleSendMessage() {
    const message = messageInput.value.trim();

    if (!message || isProcessing) {
        return;
    }

    // Add user message to chat
    addMessage(message, 'user');
    messageInput.value = '';

    // Show loading
    const loadingId = addLoadingMessage();
    isProcessing = true;
    sendButton.disabled = true;

    try {
        // Send query to API
        const response = await fetch(`${API_BASE_URL}/api/ai-agent/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                session_id: sessionId,
                context: {
                    current_page: window.location.hash || '#dashboard'
                }
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Update session ID
        if (data.session_id) {
            sessionId = data.session_id;
        }

        // Remove loading and add bot response
        removeLoadingMessage(loadingId);
        addMessage(data.content, 'bot', data.tool_used);

        // Handle Navigation
        if (data.target_route) {
            const page = data.target_route.replace('#', '');
            setTimeout(() => {
                navigateTo(page);
            }, 1000); // Small delay so user can read the confirmation
        }

    } catch (error) {
        console.error('Error:', error);
        removeLoadingMessage(loadingId);
        addMessage(
            'Sorry, I encountered an error processing your request. Please try again.',
            'bot',
            null,
            true
        );
    } finally {
        isProcessing = false;
        sendButton.disabled = false;
        messageInput.focus();
    }
}

// Add message to chat
function addMessage(text, type, toolUsed = null, isError = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;

    const contentDiv = document.createElement('div');
    contentDiv.className = `message-content ${isError ? 'error-message' : ''}`;

    // Format text (preserve line breaks)
    const formattedText = formatMessage(text);
    contentDiv.innerHTML = formattedText;

    // Add tool badge if available
    if (toolUsed && !isError) {
        const toolBadge = document.createElement('div');
        toolBadge.className = 'tool-badge';
        toolBadge.textContent = `Using: ${toolUsed}`;
        contentDiv.appendChild(toolBadge);
    }

    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return messageDiv;
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

        if (bytes.length === 0) return;

        pendingAudioChunks.push(bytes);
        pendingAudioMimeType = mimeType || pendingAudioMimeType || 'audio/pcm;rate=24000';
    } catch (error) {
        console.error('Error buffering audio response:', error);
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
        addMessage('🔊 Playing audio response...', 'bot');
        hasShownAudioIndicator = true;
    }

    if (!isPlayingAudio) {
        playNextAudio();
    }
}

function isNavigationPayload(text) {
    if (!text) return false;
    if (typeof text !== 'string') return false;
    const trimmed = text.trim();
    if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return false;
    try {
        const parsed = JSON.parse(trimmed);
        return (
            parsed &&
            typeof parsed === 'object' &&
            (typeof parsed.page === 'string' || typeof parsed.destination === 'string')
        );
    } catch (error) {
        return false;
    }
}

function speakTextResponse(text) {
    if (!text) return;
    if (!('speechSynthesis' in window)) {
        addMessage('Audio playback not supported in this browser.', 'bot');
        return;
    }

    try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = isArabicText(text) ? 'ar-SA' : 'en-US';
        utterance.onend = () => {
            updateConnectionStatus('connected', 'Ready');
        };
        utterance.onerror = () => {
            updateConnectionStatus('connected', 'Ready');
        };
        updateConnectionStatus('connected', 'Speaking...');
        window.speechSynthesis.speak(utterance);
    } catch (error) {
        console.error('Speech synthesis failed:', error);
    }
}

function isArabicText(text) {
    return /[\u0600-\u06FF]/.test(text);
}

function playNextAudio() {
    if (audioQueue.length === 0) {
        isPlayingAudio = false;
        hasShownAudioIndicator = false;
        activeAudio = null;
        updateConnectionStatus('connected', 'Ready');
        return;
    }

    isPlayingAudio = true;
    const audioUrl = audioQueue.shift();
    const audio = new Audio(audioUrl);
    audio.autoplay = true;
    activeAudio = audio;

    audio.onended = () => {
        URL.revokeObjectURL(audioUrl);
        if (activeAudio === audio) {
            activeAudio = null;
        }
        playNextAudio();
    };

    audio.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        if (activeAudio === audio) {
            activeAudio = null;
        }
        playNextAudio();
    };

    audio.play().catch(() => {
        addMessage('Click anywhere to enable audio playback.', 'bot');
    });
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

    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeString(view, 8, 'WAVE');
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
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

// Format message text
function formatMessage(text) {
    // Convert line breaks to <br>
    let formatted = text.replace(/\n/g, '<br>');

    // Convert markdown-style bold (**text**)
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Convert markdown-style italic (*text*)
    formatted = formatted.replace(/(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

    return formatted;
}

// Add loading message
function addLoadingMessage() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message';
    loadingDiv.id = `loading-${Date.now()}`;

    const loadingContent = document.createElement('div');
    loadingContent.className = 'loading';

    const dots = document.createElement('div');
    dots.className = 'loading-dots';
    dots.innerHTML = '<div class="loading-dot"></div><div class="loading-dot"></div><div class="loading-dot"></div>';

    loadingContent.appendChild(document.createTextNode('Thinking'));
    loadingContent.appendChild(dots);
    loadingDiv.appendChild(loadingContent);

    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return loadingDiv.id;
}

// Remove loading message
function removeLoadingMessage(loadingId) {
    const loadingElement = document.getElementById(loadingId);
    if (loadingElement) {
        loadingElement.remove();
    }
}

// Update connection status (for WebSocket if needed in future)
function updateConnectionStatus(status, text) {
    const statusDot = connectionStatus.querySelector('.status-dot');
    const statusText = connectionStatus.querySelector('span:last-child');

    if (status === 'connected') {
        statusDot.style.background = '#4caf50';
    } else if (status === 'disconnected') {
        statusDot.style.background = '#f44336';
    } else {
        statusDot.style.background = '#ff9800';
    }

    if (statusText) {
        statusText.textContent = text || 'Ready';
    }
}

// --- Football Analytics Section ---
let lastTrackingData = null;
let currentFrameIndex = 0;
let animationId = null;

function renderFootballPage() {
    pageContent.style.padding = '32px';
    pageContent.style.overflow = 'auto';

    pageContent.innerHTML = `
        <div class="football-container">
            <div id="footballUploadCard" class="football-upload-card">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="17 8 12 3 7 8"></polyline>
                    <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
                <h3>Upload Match Video</h3>
                <p>Drag and drop or click to upload MP4 for tactical analysis</p>
                <input type="file" id="footballVideoInput" style="display: none;" accept="video/mp4" />
                <div id="footballUploadStatus" class="football-upload-status"></div>
            </div>

            <div id="footballResults" class="football-results-container">
                <div id="videoCard" class="video-view-card hidden">
                    <video id="annotatedVideo" controls></video>
                </div>
                
                <div id="processingOverlay" class="processing-overlay hidden">
                    <div class="spinner"></div>
                    <p id="processingText">Processing Tracking Data...</p>
                </div>

                <div class="stats-sidebar">
                    <div class="stat-card possession-card">
                        <h4>Ball Possession</h4>
                        <div class="possession-stats">
                            <div class="team-stat">
                                <span id="homeTeamAbbr">HOME</span>
                                <span id="homePossessionTime">00:00</span>
                            </div>
                            <div class="team-stat">
                                <span id="awayTeamAbbr">AWAY</span>
                                <span id="awayPossessionTime">00:00</span>
                            </div>
                        </div>
                        <div class="possession-bar-container">
                            <div id="homePosFill" class="home-fill" style="width: 50%">50%</div>
                            <div id="awayPosFill" class="away-fill" style="width: 50%">50%</div>
                        </div>
                    </div>
                    <div class="stat-card">
                        <h4>Current Possession</h4>
                        <div id="possessionStat" class="stat-value">-</div>
                    </div>
                    <div class="stat-card">
                        <h4>Frames Processed</h4>
                        <div id="framesStat" class="stat-value">0 / 0</div>
                    </div>
                    <div class="stat-card">
                        <h4>Active Players</h4>
                        <div id="playerCountStat" class="stat-value">0</div>
                    </div>
                </div>
            </div>
        </div>
    `;

    const uploadCard = document.getElementById('footballUploadCard');
    const videoInput = document.getElementById('footballVideoInput');

    if (uploadCard && videoInput) {
        uploadCard.addEventListener('click', () => videoInput.click());
        videoInput.addEventListener('change', handleFootballVideoUpload);
    }
}

async function handleFootballVideoUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const statusEl = document.getElementById('footballUploadStatus');
    const overlay = document.getElementById('processingOverlay');
    const resultsContainer = document.getElementById('footballResults');

    statusEl.textContent = `Uploading ${file.name}...`;
    statusEl.className = 'football-upload-status processing';
    overlay.classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${API_BASE_URL}/api/football/tracking`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Tracking failed');

        const data = await response.json();
        lastTrackingData = data;

        statusEl.textContent = `✓ Processed ${data.frames.length} frames!`;
        statusEl.className = 'football-upload-status success';

        // Update video if provided
        if (data.video_url) {
            const videoCard = document.getElementById('videoCard');
            const video = document.getElementById('annotatedVideo');
            if (video && videoCard) {
                video.src = `${API_BASE_URL}${data.video_url}`;
                videoCard.classList.remove('hidden');
                video.play().catch(e => console.log('Auto-play blocked'));
            }
        }

        // Update stats summary
        const lastFrame = data.frames[data.frames.length - 1];
        document.getElementById('possessionStat').textContent = lastFrame.possession.team || 'None';
        document.getElementById('framesStat').textContent = `${data.frames.length} / ${data.frames.length}`;
        document.getElementById('playerCountStat').textContent = lastFrame.players.length;

        updatePossessionUI(lastFrame.possession, data.metadata);

        // Optional: Sync stats with video playback
        const video = document.getElementById('annotatedVideo');
        if (video) {
            video.addEventListener('timeupdate', () => {
                const frameIndex = Math.floor(video.currentTime * data.metadata.fps);
                if (frameIndex < data.frames.length) {
                    const frame = data.frames[frameIndex];
                    updatePossessionUI(frame.possession);
                    document.getElementById('possessionStat').textContent = frame.possession.team || 'None';
                    document.getElementById('playerCountStat').textContent = frame.players.length;
                    document.getElementById('framesStat').textContent = `${frameIndex} / ${data.frames.length}`;
                }
            });
        }
    } catch (error) {
        console.error('Football upload error:', error);
        statusEl.textContent = `✗ Error: ${error.message}`;
        statusEl.className = 'football-upload-status error';
    } finally {
        overlay.classList.add('hidden');
        if (e.target) e.target.value = '';
    }
}

function updatePossessionUI(possessionData, metadata = null) {
    if (metadata) {
        document.getElementById('homeTeamAbbr').textContent = metadata.home.abbr;
        document.getElementById('awayTeamAbbr').textContent = metadata.away.abbr;
    }

    document.getElementById('homePossessionTime').textContent = possessionData.home_time;
    document.getElementById('awayPossessionTime').textContent = possessionData.away_time;

    const homePct = possessionData.home_pct;
    const awayPct = possessionData.away_pct;

    const homeFill = document.getElementById('homePosFill');
    const awayFill = document.getElementById('awayPosFill');

    if (homeFill && awayFill) {
        homeFill.style.width = `${homePct}%`;
        homeFill.textContent = homePct > 10 ? `${homePct}%` : '';

        awayFill.style.width = `${awayPct}%`;
        awayFill.textContent = awayPct > 10 ? `${awayPct}%` : '';

        if (metadata) {
            // Convert BGR (Python) to RGB (JS)
            const hColor = metadata.home.color;
            const aColor = metadata.away.color;
            homeFill.style.backgroundColor = `rgb(${hColor[2]}, ${hColor[1]}, ${hColor[0]})`;
            awayFill.style.backgroundColor = `rgb(${aColor[2]}, ${aColor[1]}, ${aColor[0]})`;
        }
    }
}

// Drawing logic removed as pitch canvas is no longer used
