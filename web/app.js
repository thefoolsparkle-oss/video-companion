/**
 * app.js — AI VTuber 主项目前端逻辑
 *
 * 包含: 会话管理 / WebSocket / avatar_state / 音频播放 / 硬件验收
 * 所有敏感硬件默认关闭，需用户手动开启。
 */

const App = (() => {
  'use strict';

  const VC_HOST = '127.0.0.1:8001';
  const VC_WS = `ws://${VC_HOST}/ws`;
  const VC_API = `http://${VC_HOST}`;

  let ws = null;
  let sessionActive = false;
  let sessionStart = 0;
  let turnCount = 0;
  let timerId = null;

  // 硬件状态
  let camStream = null;
  let camInterval = null;
  let camFrames = 0;
  let camActive = false;

  let micStream = null;
  let micCtx = null;
  let micActive = false;
  let micSegments = 0;

  const $ = (s) => document.querySelector(s);

  // ========== 会话 ==========
  async function startSession() {
    try {
      const r = await fetch(`${VC_API}/api/session/start?persona_id=default`, { method: 'POST' });
      const data = await r.json();
      if (data.status !== 'started') throw new Error('Start failed');

      sessionActive = true;
      sessionStart = Date.now();
      turnCount = 0;

      $('#btn-session').disabled = true;
      $('#btn-stop').disabled = false;
      $('#btn-send').disabled = false;
      $('#text-input').disabled = false;
      $('#summary-bar').classList.remove('show');
      $('#label-session').textContent = '会话中';

      connectWS();
      startTimer();
      addMsg('system', '会话已开始');
    } catch (e) {
      addMsg('system', '启动失败: ' + e.message);
    }
  }

  async function stopSession() {
    try {
      const r = await fetch(`${VC_API}/api/session/stop`, { method: 'POST' });
      const data = await r.json();
      if (data.status !== 'stopped') throw new Error('Stop failed');

      sessionActive = false;
      if (ws) { ws.close(); ws = null; }
      stopTimer();

      $('#btn-session').disabled = false;
      $('#btn-stop').disabled = true;
      $('#btn-send').disabled = true;
      $('#text-input').disabled = true;
      $('#label-session').textContent = '已结束';

      const s = data.summary;
      $('#summary-text').textContent = s.summary_text || '(无内容)';
      $('#summary-dur').textContent = (s.duration_sec || 0).toFixed(0) + 's';
      $('#summary-turns').textContent = s.total_turns;
      $('#summary-bar').classList.add('show');

      addMsg('system', `会话结束 · ${(s.duration_sec||0).toFixed(0)}s · ${s.total_turns} 轮`);
    } catch (e) {
      addMsg('system', '停止失败: ' + e.message);
    }
  }

  // ========== WebSocket ==========
  function connectWS() {
    if (ws) { try { ws.close(); } catch(e){} }
    ws = new WebSocket(VC_WS);
    ws.onopen = () => setDot('dot-ws', true);
    ws.onclose = () => { setDot('dot-ws', false); if (sessionActive) setTimeout(connectWS, 3000); };
    ws.onerror = () => {};
    ws.onmessage = (ev) => {
      try { handleMessage(JSON.parse(ev.data)); } catch (e) {}
    };
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case 'status':
        addMsg('system', `状态: ${msg.data.session_state}`);
        break;
      case 'ai_response':
        addMsg('ai', msg.text);
        updateAvatar(msg.avatar_state);
        playAudio(msg.audio_base64, msg.audio_format);
        turnCount = msg.turn_id || turnCount;
        $('#label-turns').textContent = turnCount;
        break;
      case 'observation':
        updateObservation(msg.data);
        break;
      case 'system_error':
        addMsg('system', `[${msg.code}] ${msg.message}`);
        break;
      case 'interrupted':
        addMsg('system', '播放已中断');
        break;
    }
  }

  // ========== Avatar ==========
  function updateAvatar(state) {
    if (!state) return;
    const card = $('#avatar-card');
    const mouth = $('#mouth-bar');
    $('#av-expression').textContent = state.expression || '-';
    $('#av-speaking').textContent = state.speaking;
    $('#av-looking').textContent = state.looking_at_user;

    if (state.speaking) { card.classList.add('talking'); mouth.classList.add('open'); }
    else { card.classList.remove('talking'); mouth.classList.remove('open'); }

    const emoji = { talking:'🗣️', happy:'😊', neutral:'😶', thinking:'🤔', surprised:'😮', sad:'😔', idle:'💤' };
    $('#avatar-face').textContent = emoji[state.expression] || '😶';
  }

  function updateObservation(data) {
    const el = $('#hw-presence');
    el.textContent = data.presence_status || 'unknown';
    el.className = 'presence-tag ' + (data.presence_status || 'unknown');
    $('#obs-raw').textContent = JSON.stringify(data, null, 2);
  }

  // ========== 音频播放 ==========
  function playAudio(b64, fmt) {
    if (!b64) return;
    try {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'audio/' + (fmt || 'mp3') });
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      a.play().catch(() => {});
      a.onended = () => URL.revokeObjectURL(url);
    } catch(e) {}
  }

  // ========== 聊天 ==========
  function sendText() {
    const input = $('#text-input');
    const text = input.value.trim();
    if (!text || !sessionActive || !ws || ws.readyState !== WebSocket.OPEN) return;
    input.value = '';
    ws.send(JSON.stringify({ type: 'text_input', text }));
    addMsg('user', text);
  }

  function addMsg(speaker, text) {
    const el = $('#messages');
    const ph = el.querySelector('.placeholder-msg');
    if (ph) ph.remove();
    const div = document.createElement('div');
    div.className = 'msg ' + speaker;
    div.textContent = text;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
  }

  // ========== 摄像头验收 ==========
  async function toggleCamera() {
    if (camActive) { stopCamera(); return; }
    try {
      camStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 320 }, height: { ideal: 240 }, facingMode: 'user' },
        audio: false,
      });
      camActive = true;
      camFrames = 0;
      setDot('dot-cam', true);
      $('#btn-cam-toggle').textContent = '关闭';
      $('#cam-error').style.display = 'none';

      const video = $('#cam-preview');
      video.srcObject = camStream;
      video.play();

      startFrameCapture();
    } catch (e) {
      camActive = false;
      setDot('dot-cam', false);
      showCamError('摄像头不可用: ' + (e.name || e.message));
    }
  }

  function stopCamera() {
    camActive = false;
    stopFrameCapture();
    if (camStream) { camStream.getTracks().forEach(t => t.stop()); camStream = null; }
    $('#cam-preview').srcObject = null;
    setDot('dot-cam', false);
    $('#btn-cam-toggle').textContent = '开启';
    $('#cam-frames').textContent = '0';
    $('#hw-presence').textContent = '-';
    $('#hw-presence').className = 'presence-tag unknown';
  }

  function startFrameCapture() {
    if (camInterval) return;
    camInterval = setInterval(() => {
      if (!camActive || !camStream) return;
      const video = $('#cam-preview');
      if (!video.videoWidth) return;
      const canvas = $('#cam-canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0);
      try {
        const b64 = canvas.toDataURL('image/jpeg', 0.7).split(',')[1];
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'frame', data: b64,
            width: canvas.width, height: canvas.height, format: 'jpeg',
          }));
          camFrames++;
          $('#cam-frames').textContent = camFrames;
        }
      } catch(e) {}
    }, 2000);
  }

  function stopFrameCapture() {
    if (camInterval) { clearInterval(camInterval); camInterval = null; }
  }

  function showCamError(msg) {
    const el = $('#cam-error');
    el.textContent = msg;
    el.style.display = 'block';
  }

  // ========== 麦克风验收 ==========
  function updateMicDebug(state, level, ctxState, trackState) {
    const el = $('#mic-debug');
    if (!el) return;
    el.style.display = 'block';
    el.textContent = `Mic: ${state} | Level: ${level} | Ctx: ${ctxState} | Track: ${trackState}`;
  }

  async function toggleMic() {
    if (micActive) { stopMic(); return; }
    updateMicDebug('starting', '0.00', '--', '--');
    try {
      micStream = await getUserMediaWithFallback();
      const track = micStream.getAudioTracks()[0];
      updateMicDebug('live', '0.00', '--', track ? track.readyState : '?');
      micActive = true;
      micSegments = 0;
      setDot('dot-mic', true);
      $('#btn-mic-toggle').textContent = '关闭';
      $('#mic-error').style.display = 'none';
      await startMicMeter(micStream);
      startMicCapture(micStream);
    } catch (e) {
      micActive = false;
      setDot('dot-mic', false);
      $('#btn-mic-toggle').textContent = '开启';
      showMicError('麦克风不可用: ' + (e.name || e.message));
      addMsg('system', '麦克风启动失败: ' + (e.name || '') + ' ' + (e.message || ''));
      updateMicDebug('error', '0.00', '--', '--');
      console.error('toggleMic error:', e);
    }
  }

  async function getUserMediaWithFallback() {
    try {
      return await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (e) {
      console.warn('getUserMedia with constraints failed, falling back: ' + e.message);
      return await navigator.mediaDevices.getUserMedia({ audio: true });
    }
  }

  function stopMic() {
    micActive = false;
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (micCtx) {
      try { micCtx.close(); } catch(e) {}
      micCtx = null;
    }
    setDot('dot-mic', false);
    $('#btn-mic-toggle').textContent = '开启';
    $('#mic-meter').style.width = '0%';
    $('#mic-error').style.display = 'none';
    updateMicDebug('off', '0.00', 'closed', 'ended');
    const dbg = $('#mic-debug');
    if (dbg) dbg.style.display = 'none';
  }

  async function startMicMeter(stream) {
    micCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    console.debug('AudioContext created, state:', micCtx.state);
    if (micCtx.state === 'suspended') {
      await micCtx.resume();
      console.debug('AudioContext resumed, state:', micCtx.state);
    }
    const src = micCtx.createMediaStreamSource(stream);
    const analyser = micCtx.createAnalyser();
    analyser.fftSize = 256;
    src.connect(analyser);
    const buf = new Uint8Array(analyser.frequencyBinCount);
    let tickCount = 0;

    function tick() {
      if (!micActive || !micCtx) {
        $('#mic-meter').style.width = '0%';
        return;
      }
      analyser.getByteFrequencyData(buf);
      const avg = buf.reduce((a, b) => a + b, 0) / buf.length;
      const pct = Math.min(100, Math.round(avg * 2));
      $('#mic-meter').style.width = pct + '%';

      tickCount++;
      if (tickCount % 60 === 1) {
        const track = micStream ? micStream.getAudioTracks()[0] : null;
        console.debug('mic tick #' + tickCount + ' avg=' + avg.toFixed(2) + ' pct=' + pct + ' ctx=' + micCtx.state + ' track=' + (track ? track.readyState + (track.muted ? '/muted' : '/unmuted') : 'null'));
        updateMicDebug('live', avg.toFixed(2), micCtx.state, track ? track.readyState + (track.muted ? ' muted' : '') : '?');
      }
      requestAnimationFrame(tick);
    }
    tick();
  }

  function startMicCapture(stream) {
    const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
    let recorder;
    let chunks = [];
    let silenceTimer = null;

    try {
      recorder = new MediaRecorder(stream, { mimeType: mime });
    } catch(e) {
      // MediaRecorder not available, mic meter still works
      return;
    }

    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };

    // 每 3 秒发一段语音（模拟完整话语，用于验证链路）
    async function segmentLoop() {
      if (!micActive) return;
      chunks = [];
      try {
        if (recorder.state === 'inactive') recorder.start(200);
      } catch(e) {}

      silenceTimer = setTimeout(async () => {
        try {
          if (recorder.state === 'recording') recorder.stop();
        } catch(e) {}

        // 等 recorder 把数据收完
        await new Promise(r => setTimeout(r, 500));

        if (chunks.length && ws && ws.readyState === WebSocket.OPEN && sessionActive) {
          const blob = new Blob(chunks, { type: mime });
          const b64 = await blobToBase64(blob);
          ws.send(JSON.stringify({
            type: 'speech_input', data: b64,
            duration_ms: 3000, sample_rate: 16000,
            vad_ended: true, vad_text: '',
          }));
          micSegments++;
          $('#mic-segments').textContent = micSegments;
        }
        chunks = [];
        segmentLoop();
      }, 3000);
    }
    segmentLoop();
  }

  function showMicError(msg) {
    const el = $('#mic-error');
    el.textContent = msg;
    el.style.display = 'block';
  }

  // ========== 工具 ==========
  function blobToBase64(blob) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const r = reader.result;
        const i = r.indexOf('base64,');
        resolve(i >= 0 ? r.substring(i + 7) : r);
      };
      reader.readAsDataURL(blob);
    });
  }

  function setDot(id, on) {
    $(`#${id}`).className = 'dot ' + (on ? 'on' : 'off');
  }

  // ========== Timer ==========
  function startTimer() {
    stopTimer();
    timerId = setInterval(() => {
      if (!sessionActive) return;
      const sec = Math.floor((Date.now() - sessionStart) / 1000);
      const m = String(Math.floor(sec / 60)).padStart(2, '0');
      const s = String(sec % 60).padStart(2, '0');
      $('#label-timer').textContent = m + ':' + s;
    }, 1000);
  }
  function stopTimer() { if (timerId) { clearInterval(timerId); timerId = null; } }

  // ========== 初始化 ==========
  async function init() {
    try {
      const r = await fetch(`${VC_API}/api/health`);
      if (r.ok) setDot('dot-vc', true);
    } catch(e) {
      setDot('dot-vc', false);
      addMsg('system', 'video-companion 未连接');
      return;
    }

    // 键盘
    $('#text-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendText();
    });
  }

  init();

  return { startSession, stopSession, sendText, toggleCamera, toggleMic };
})();
