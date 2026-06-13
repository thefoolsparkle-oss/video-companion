/**
 * app.js — AI VTuber 主项目前端逻辑
 *
 * 职责：
 * - 连接 video-companion WebSocket
 * - 管理 session (start / stop)
 * - 发送 text_input，接收 ai_response
 * - 更新占位角色 (avatar_state)
 * - 播放 audio_base64
 * - 显示 transcript 和 summary
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

  // ========== DOM refs ==========
  const $ = (s) => document.querySelector(s);

  // ========== Session ==========
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
      if (ws) ws.close();
      stopTimer();

      $('#btn-session').disabled = false;
      $('#btn-stop').disabled = true;
      $('#btn-send').disabled = true;
      $('#text-input').disabled = true;
      $('#label-session').textContent = '已结束';

      const s = data.summary;
      $('#summary-text').textContent = s.summary_text;
      $('#summary-dur').textContent = s.duration_sec.toFixed(0) + 's';
      $('#summary-turns').textContent = s.total_turns;
      $('#summary-bar').classList.add('show');

      addMsg('system', `会话结束 · ${s.duration_sec.toFixed(0)}s · ${s.total_turns} 轮`);
    } catch (e) {
      addMsg('system', '停止失败: ' + e.message);
    }
  }

  // ========== WebSocket ==========
  function connectWS() {
    ws = new WebSocket(VC_WS);
    ws.onopen = () => {
      setStatus('dot-ws', true, 'label-ws', 'WS 已连接');
    };
    ws.onclose = () => {
      setStatus('dot-ws', false, 'label-ws', 'WS 断开');
      if (sessionActive) setTimeout(connectWS, 3000);
    };
    ws.onerror = () => {};
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        handleMessage(msg);
      } catch (e) { /* ignore */ }
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
        updatePresence(msg.data.presence_status);
        break;

      case 'system_error':
        addMsg('system', `[${msg.code}] ${msg.message}`);
        break;

      case 'interrupted':
        addMsg('system', '播放已中断');
        break;

      case 'transcript':
        // ai_response 已处理，transcript 做冗余记录
        break;
    }
  }

  // ========== Avatar ==========
  function updateAvatar(state) {
    if (!state) return;
    const card = $('#avatar-card');
    const mouth = $('#mouth-bar');
    const face = $('#avatar-face');

    $('#av-expression').textContent = state.expression;
    $('#av-speaking').textContent = state.speaking;
    $('#av-looking').textContent = state.looking_at_user;

    if (state.speaking) {
      card.classList.add('talking');
      mouth.classList.add('open');
    } else {
      card.classList.remove('talking');
      mouth.classList.remove('open');
    }

    const emoji = {
      talking: '🗣️', happy: '😊', neutral: '😶', thinking: '🤔',
      surprised: '😮', sad: '😔', idle: '💤'
    };
    face.textContent = emoji[state.expression] || '😶';
  }

  function updatePresence(status) {
    const el = $('#av-presence');
    el.textContent = status;
    el.className = 'presence-tag ' + status;
  }

  // ========== Audio ==========
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
    } catch (e) { /* ignore */ }
  }

  // ========== Chat ==========
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

  function stopTimer() {
    if (timerId) { clearInterval(timerId); timerId = null; }
  }

  // ========== Status ==========
  function setStatus(dotId, on, labelId, text) {
    $(`#${dotId}`).className = 'dot ' + (on ? 'on' : 'off');
    $(`#${labelId}`).textContent = text;
  }

  // ========== Init ==========
  async function init() {
    // Check video-companion health
    try {
      const r = await fetch(`${VC_API}/api/health`);
      if (r.ok) setStatus('dot-vc', true, 'label-vc', 'video-companion 在线');
    } catch (e) {
      setStatus('dot-vc', false, 'label-vc', 'video-companion 离线');
      addMsg('system', 'video-companion 未连接，请先启动服务');
      return;
    }

    // Keyboard shortcut
    $('#text-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendText();
    });
  }

  init();

  // ========== Public API ==========
  return { startSession, stopSession, sendText };
})();
