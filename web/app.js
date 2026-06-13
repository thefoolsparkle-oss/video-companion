/**
 * Video Companion 前端逻辑 (v0.3-dev)
 *
 * AI VTuber 实时感知与互动核心前端。
 * 独立运行模式，不依赖主项目。
 */

(function () {
    'use strict';

    // ============ 状态 ============
    const S = {
        connected: false,
        ws: null,
        reconnectTimer: null,
        sessionActive: false,

        consent: { camera: false, microphone: false, external_vision: false },

        // 摄像头
        videoStream: null,
        videoTrack: null,
        frameInterval: null,
        frameCount: 0,

        // 麦克风
        audioContext: null,
        audioStream: null,
        mediaRecorder: null,
        audioChunks: [],
        isRecording: false,
        recordingStartTime: 0,
        silenceTimer: null,
        lastSpeechTime: 0,

        // 播放
        currentAudio: null,
        playbackQueue: [],

        // 轮询
        pollTimer: null,
        durationTimer: null,
        sessionStartTime: 0,
    };

    const $ = (sel) => document.querySelector(sel);

    // ============ WebSocket ============
    function connectWS() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/ws`;

        S.ws = new WebSocket(url);
        S.ws.onopen = () => {
            S.connected = true;
            updateConnectionUI(true);
            console.log('[WS] Connected');
        };
        S.ws.onclose = () => {
            S.connected = false;
            updateConnectionUI(false);
            console.log('[WS] Disconnected, reconnecting...');
            scheduleReconnect();
        };
        S.ws.onerror = () => { /* handled by onclose */ };
        S.ws.onmessage = (ev) => {
            try { handleMessage(JSON.parse(ev.data)); }
            catch (e) { console.error('[WS] Parse error:', e); }
        };
    }

    function scheduleReconnect() {
        if (S.reconnectTimer) return;
        S.reconnectTimer = setTimeout(() => {
            S.reconnectTimer = null;
            if (!S.connected) connectWS();
        }, 3000);
    }

    function send(msg) {
        if (S.ws && S.ws.readyState === WebSocket.OPEN) {
            S.ws.send(JSON.stringify(msg));
        }
    }

    function handleMessage(msg) {
        switch (msg.type) {
            case 'pong': break;
            case 'status': updateStatusFromServer(msg.data); break;
            case 'observation': updateObservation(msg.data, msg.external); break;
            case 'ai_response': playAIResponse(msg); break;
            case 'transcript': addTranscript(msg.speaker, msg.text, msg.turn_id); break;
            case 'interrupted': onInterrupted(); break;
            case 'consent_changed': syncConsentUI(msg.state); break;
            case 'system_error': showSystemError(msg.code, msg.message); break;
            case 'error': showError(msg.message); break;
        }
    }

    function updateConnectionUI(ok) {
        const el = $('#connection-status');
        el.textContent = ok ? '已连接' : '未连接';
        el.className = 'status-badge ' + (ok ? 'connected' : 'disconnected');
    }

    // ============ 摄像头 ============
    async function startCamera() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user',
                },
                audio: false,
            });
            S.videoStream = stream;
            S.videoTrack = stream.getVideoTracks()[0];
            $('#camera-preview').srcObject = stream;
            $('#camera-overlay').classList.add('hidden');
            $('#camera-status').textContent = '摄像头: 已开启';
            startFrameCapture();
            return true;
        } catch (err) {
            console.error('Camera error:', err);
            $('#camera-status').textContent = '摄像头: ' + err.message;
            return false;
        }
    }

    function stopCamera() {
        stopFrameCapture();
        if (S.videoStream) {
            S.videoStream.getTracks().forEach(t => t.stop());
            S.videoStream = null;
            S.videoTrack = null;
        }
        $('#camera-preview').srcObject = null;
        $('#camera-overlay').classList.remove('hidden');
        $('#camera-status').textContent = '摄像头: 关闭';
    }

    function startFrameCapture() {
        if (S.frameInterval) return;
        let counter = 0;
        S.frameInterval = setInterval(() => {
            if (!S.videoTrack || S.videoTrack.readyState !== 'live') return;
            captureAndSendFrame();
            counter++;
            $('#frame-count').textContent = '帧: ' + counter;
        }, 2000);
    }

    function stopFrameCapture() {
        if (S.frameInterval) {
            clearInterval(S.frameInterval);
            S.frameInterval = null;
        }
    }

    function captureAndSendFrame() {
        const video = $('#camera-preview');
        const canvas = $('#camera-canvas');
        if (!video.videoWidth || !video.videoHeight) return;

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);

        try {
            const base64 = canvas.toDataURL('image/jpeg', 0.7).split(',')[1];
            send({
                type: 'frame',
                data: base64,
                width: canvas.width,
                height: canvas.height,
                format: 'jpeg',
            });
        } catch (e) { /* ignore */ }
    }

    // ============ 麦克风 ============
    async function startMicrophone() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                },
            });
            S.audioStream = stream;
            initAudioRecording(stream);
            return true;
        } catch (err) {
            console.error('Microphone error:', err);
            return false;
        }
    }

    function initAudioRecording(stream) {
        try {
            S.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000,
            });
            const source = S.audioContext.createMediaStreamSource(stream);
            const analyser = S.audioContext.createAnalyser();
            analyser.fftSize = 256;
            source.connect(analyser);

            // VAD via analyser
            const bufferLength = analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            let isSpeaking = false;
            let silenceStart = 0;
            const SILENCE_THRESHOLD = 800; // ms
            const SPEECH_THRESHOLD = 25;   // amplitude

            function checkVAD() {
                if (!S.audioContext || S.audioContext.state === 'closed') return;
                analyser.getByteFrequencyData(dataArray);
                const avg = dataArray.reduce((a, b) => a + b, 0) / bufferLength;

                // Update visualizer
                updateVisualizer(avg);

                const now = Date.now();
                if (avg > SPEECH_THRESHOLD) {
                    if (!isSpeaking) {
                        isSpeaking = true;
                        S.lastSpeechTime = now;
                    }
                    silenceStart = 0;
                } else if (isSpeaking) {
                    if (silenceStart === 0) silenceStart = now;
                    if (now - silenceStart > SILENCE_THRESHOLD) {
                        // end of speech segment
                        isSpeaking = false;
                        silenceStart = 0;
                        stopAudioSegment();
                    }
                }

                if (isSpeaking && S.audioChunks.length === 0) {
                    startAudioSegment();
                }

                requestAnimationFrame(checkVAD);
            }

            // MediaRecorder for actual audio capture
            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus' : 'audio/webm';
            S.mediaRecorder = new MediaRecorder(stream, { mimeType });

            S.mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) S.audioChunks.push(e.data);
            };

            requestAnimationFrame(checkVAD);
        } catch (e) {
            console.error('Audio init error:', e);
        }
    }

    function startAudioSegment() {
        S.audioChunks = [];
        S.recordingStartTime = Date.now();
        try {
            if (S.mediaRecorder && S.mediaRecorder.state === 'inactive') {
                S.mediaRecorder.start(200); // 200ms chunks
            }
        } catch (e) { /* ignore */ }
    }

    function stopAudioSegment() {
        try {
            if (S.mediaRecorder && S.mediaRecorder.state === 'recording') {
                S.mediaRecorder.stop();
            }
        } catch (e) { /* ignore */ }

        // Collect and send to backend for ASR
        setTimeout(async () => {
            if (S.audioChunks.length === 0) return;
            const blob = new Blob(S.audioChunks, { type: 'audio/webm' });
            try {
                const base64 = await blobToBase64(blob);
                send({
                    type: 'speech_input',
                    data: base64,
                    duration_ms: Date.now() - S.recordingStartTime,
                    sample_rate: 16000,
                    vad_ended: true,
                    vad_text: '', // 交给后端 ASR 处理
                    confidence: 0,
                });
            } catch (e) {
                console.error('Audio send error:', e);
            }
            S.audioChunks = [];
        }, 300);
    }

    // trySpeechRecognition removed — browser SpeechRecognition cannot transcribe
    // recorded audio chunks reliably. Backend ASR (OpenAI Whisper) is the
    // primary transcription path.

    function stopMicrophone() {
        if (S.mediaRecorder && S.mediaRecorder.state !== 'inactive') {
            try { S.mediaRecorder.stop(); } catch (e) { /* ignore */ }
        }
        if (S.audioStream) {
            S.audioStream.getTracks().forEach(t => t.stop());
            S.audioStream = null;
        }
        if (S.audioContext) {
            S.audioContext.close().catch(() => {});
            S.audioContext = null;
        }
        S.mediaRecorder = null;
        S.audioChunks = [];
    }

    // ============ 语音播放 ============
    function playAIResponse(msg) {
        const text = msg.text || '';
        const audioB64 = msg.audio_base64 || '';

        // Show in transcript
        addTranscript('ai', text, msg.turn_id);

        // Play audio if available
        if (audioB64) {
            playAudioBase64(audioB64, msg.audio_format || 'mp3');
        }
    }

    function playAudioBase64(b64, format) {
        // Interrupt current
        if (S.currentAudio) {
            S.currentAudio.pause();
            S.currentAudio = null;
        }

        try {
            const binary = atob(b64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            const blob = new Blob([bytes], { type: 'audio/' + (format || 'mp3') });
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);

            S.currentAudio = audio;
            audio.onended = () => {
                S.currentAudio = null;
                URL.revokeObjectURL(url);
            };
            audio.onerror = () => {
                S.currentAudio = null;
                URL.revokeObjectURL(url);
            };
            audio.play().catch(() => {});
        } catch (e) {
            console.error('Audio playback error:', e);
        }
    }

    function onInterrupted() {
        if (S.currentAudio) {
            S.currentAudio.pause();
            S.currentAudio = null;
        }
        addTranscript('system', '[播放被中断]');
    }

    function updateVisualizer(amplitude) {
        const vis = $('#audio-visualizer');
        const bars = vis.querySelectorAll('.bar');
        const active = amplitude > 25;
        vis.classList.toggle('active', active);
        if (active) {
            bars.forEach((bar, i) => {
                const h = Math.min(18, Math.max(3, amplitude * 0.3 * (1 + i * 0.3)));
                bar.style.height = h + 'px';
            });
        }
    }

    // ============ UI 更新 ============
    function updateStatusFromServer(data) {
        $('#session-state').textContent = data.session_state || '未知';
        $('#session-duration').textContent = (data.duration_sec || 0).toFixed(0) + 's';
        $('#session-turns').textContent = data.total_turns || 0;
        $('#session-ext-analyzes').textContent =
            (data.vision_usage && data.vision_usage.analyze_count) || 0;
        if (data.vision_usage) {
            const cost = data.vision_usage.total_cost || 0;
            $('#session-cost').textContent = '$' + cost.toFixed(4);
        }
    }

    function updateObservation(data, external) {
        $('#obs-timestamp').textContent = data.timestamp
            ? new Date(data.timestamp * 1000).toLocaleTimeString() : '';

        const status = data.presence_status || 'unknown';
        const presenceMap = {
            'present': '✅ 检测到用户',
            'absent': '❌ 未检测到',
            'unknown': '❓ 无法判断',
            'unusable': '⚠ 画面不可用',
        };
        $('#obs-presence').textContent = presenceMap[status] || status;

        const face = data.face || {};
        $('#obs-face').textContent = face.present
            ? `检测到 (${face.rough_mood || '未知情绪'})`
            : (data.detector_available ? '未检测到' : '检测器不可用');

        const motion = data.motion || {};
        $('#obs-motion').textContent = motion.level || '未知';

        let quality = '正常';
        if (data.is_usable === false) quality = '⚠ 不佳';
        if (data.brightness < 0.05) quality = '⚠ 过暗';
        if (!data.detector_available) quality += ' (无检测器)';
        $('#obs-quality').textContent = quality;

        if (external && external.description) {
            $('#obs-external-row').style.display = 'flex';
            $('#obs-external').textContent = external.description;
        }
    }

    function syncConsentUI(state) {
        if (!state) return;
        $('#consent-camera').checked = state.camera;
        $('#consent-microphone').checked = state.microphone;
        $('#consent-vision').checked = state.external_vision;
    }

    function addTranscript(speaker, text, turnId) {
        if (!text) return;
        const log = $('#transcript-log');
        const placeholder = log.querySelector('.placeholder');
        if (placeholder) placeholder.remove();

        const entry = document.createElement('div');
        entry.className = 'transcript-entry';
        entry.innerHTML =
            '<div class="speaker ' + speaker + '">' + speaker.toUpperCase() + '</div>' +
            '<div class="text">' + escapeHtml(text) + '</div>' +
            (turnId ? '<div class="meta">Turn #' + turnId + '</div>' : '');
        log.appendChild(entry);
        log.scrollTop = log.scrollHeight;

        // Limit entries
        while (log.children.length > 100) {
            log.removeChild(log.firstChild);
        }
    }

    function showSystemError(code, msg) {
        addTranscript('system', '[错误 ' + code + '] ' + msg);
        // 不进入 AI 回复，只显示系统错误
    }

    function showError(msg) {
        addTranscript('system', '⚠ ' + msg);
    }

    // ============ 授权控制 ============
    // 授权变更全部走 WebSocket，不再同时发 REST 请求。
    // REST /api/consent 保留为只读或外部系统调用。
    $('#consent-camera').addEventListener('change', async () => {
        const g = $('#consent-camera').checked;
        S.consent.camera = g;
        if (g) await startCamera();
        else stopCamera();
        send({ type: 'consent_update', item: 'camera', granted: g });
    });

    $('#consent-microphone').addEventListener('change', async () => {
        const g = $('#consent-microphone').checked;
        S.consent.microphone = g;
        if (g) await startMicrophone();
        else stopMicrophone();
        send({ type: 'consent_update', item: 'microphone', granted: g });
    });

    $('#consent-vision').addEventListener('change', () => {
        const g = $('#consent-vision').checked;
        S.consent.external_vision = g;
        send({ type: 'consent_update', item: 'external_vision', granted: g });
    });

    // ============ 会话控制 ============
    $('#btn-start-session').addEventListener('click', async () => {
        try {
            const resp = await fetch('/api/session/start?persona_id=default', { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'started') {
                S.sessionActive = true;
                S.sessionStartTime = Date.now();
                updateSessionUI(true);
                addTranscript('system', '会话已开始');
            }
        } catch (e) { addTranscript('system', '启动失败: ' + e.message); }
    });

    $('#btn-stop-session').addEventListener('click', async () => {
        try {
            const resp = await fetch('/api/session/stop', { method: 'POST' });
            const data = await resp.json();
            if (data.status === 'stopped') {
                S.sessionActive = false;
                updateSessionUI(false);
                addTranscript('system', '会话已结束 (时长: ' +
                    (data.summary ? data.summary.duration_sec.toFixed(0) + 's, ' : '') +
                    '轮次: ' + (data.summary ? data.summary.total_turns : 0) + ')');
                stopCamera();
                stopMicrophone();
                // 同步后端授权状态到 UI
                if (data.consent) {
                    syncConsentUI(data.consent);
                } else {
                    $('#consent-camera').checked = false;
                    $('#consent-microphone').checked = false;
                    $('#consent-vision').checked = false;
                }
            }
        } catch (e) { addTranscript('system', '停止失败: ' + e.message); }
    });

    $('#btn-pause-session').addEventListener('click', () => {
        addTranscript('system', '暂停功能开发中...');
    });

    $('#btn-interrupt').addEventListener('click', () => {
        send({ type: 'interrupt' });
    });

    $('#btn-send-text').addEventListener('click', () => {
        const input = $('#text-input');
        const text = input.value.trim();
        if (!text) return;
        input.value = '';
        send({ type: 'text_input', text: text });
        addTranscript('user', text);
    });

    $('#text-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') $('#btn-send-text').click();
    });

    $('#btn-clear-transcript').addEventListener('click', () => {
        $('#transcript-log').innerHTML = '<p class="placeholder">尚无对话记录</p>';
    });

    function updateSessionUI(active) {
        $('#btn-start-session').disabled = active;
        $('#btn-stop-session').disabled = !active;
        $('#btn-pause-session').disabled = !active;
        $('#btn-interrupt').disabled = !active;
        $('#btn-send-text').disabled = !active;
        $('#session-state').textContent = active ? '运行中' : '已结束';
    }

    // ============ 轮询 ============
    async function pollStatus() {
        try {
            const resp = await fetch('/api/status');
            const data = await resp.json();
            updateStatusFromServer(data);
            if (data.consent) syncConsentUI(data.consent);
            S.sessionActive = data.session_state === 'active';
            updateSessionUI(S.sessionActive);
        } catch (e) { /* silent */ }
    }

    function startPolling() {
        if (S.pollTimer) return;
        S.pollTimer = setInterval(pollStatus, 3000);
    }

    // ============ 工具 ============
    function blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = reader.result;
                const idx = result.indexOf('base64,');
                resolve(idx >= 0 ? result.substring(idx + 7) : result);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    function escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // ============ 初始化 ============
    function init() {
        connectWS();
        startPolling();
        pollStatus();
    }

    window.addEventListener('beforeunload', () => {
        stopFrameCapture();
        stopCamera();
        stopMicrophone();
        if (S.ws) S.ws.close();
        if (S.pollTimer) clearInterval(S.pollTimer);
        if (S.reconnectTimer) clearTimeout(S.reconnectTimer);
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
