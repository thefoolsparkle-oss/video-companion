# API Contract — AI VTuber 主项目接入契约

video-companion 对外暴露两部分 API：REST 和 WebSocket。
所有输出结构已稳定，主项目可据此集成。

---

## REST API

基础 URL: `http://127.0.0.1:8001`

### GET /api/health

健康检查。

**Response** `200`:
```json
{"status": "ok"}
```

---

### GET /api/status

系统全状态。

**Response** `200`:
```json
{
  "service": "Video Companion",
  "version": "0.3.0-dev",
  "project_mode": "standalone_ai_vtuber",
  "uptime_sec": 12.3,
  "session_state": "idle",
  "duration_sec": 0.0,
  "total_turns": 0,
  "consent": {
    "camera": false,
    "microphone": false,
    "external_vision": false,
    "save_summary": false,
    "save_observation": false
  },
  "camera_metrics": {"state": "off", "frames_received": 0},
  "audio_metrics": {"state": "off", "chunks_received": 0},
  "vision_usage": {"enabled": false, "provider": "noop", "analyze_count": 0},
  "speech_stats": {"asr_provider": "mock", "tts_provider": "mock", "state": "idle"},
  "mnemosyne": {"api_base": "...", "connected": false},
  "ws_connections": 0
}
```

---

### POST /api/session/start

启动视频会话。

**Query**: `persona_id` (string, default "default")

**Response** `200`:
```json
{
  "status": "started",
  "session_state": "active",
  "persona_id": "default"
}
```

---

### POST /api/session/stop

停止视频会话，返回摘要。

**Response** `200`:
```json
{
  "status": "stopped",
  "summary": {
    "session_id": "vc-session-12345678",
    "persona_name": "Mio",
    "display_name": "澪",
    "start_time": 1718000000.0,
    "end_time": 1718000120.0,
    "duration_sec": 120.0,
    "total_turns": 6,
    "total_vision_frames": 60,
    "total_external_analyses": 0,
    "interruptions": 0,
    "errors": 0,
    "latency": {"avg_ms": 45.2, "max_ms": 120, "min_ms": 10},
    "reply_mode": "standalone_ai_vtuber",
    "summary_text": "本次会话用户说了：你好、今天天气不错、再见。收到 60 帧画面，最后视觉状态: unknown。",
    "key_topics": ["问候", "天气"],
    "visual_notes": [],
    "system_notes": ["standalone_ai_vtuber_mode"],
    "saved_locally": false
  },
  "consent": {"camera": false, "microphone": false, "external_vision": false, "save_summary": false, "save_observation": false}
}
```

**关键保证**：`summary.summary_text` 永不为空字符串。

---

### GET /api/session/status

**Response** `200`:
```json
{
  "session_state": "active",
  "persona_id": "default",
  "total_turns": 3,
  "duration_sec": 45.2,
  "latest_observation": null
}
```

---

### GET /api/session/turns?limit=20

**Response** `200`:
```json
[
  {
    "turn_id": 1,
    "user_text": "你好",
    "ai_response": "晚上好！我是澪，有什么想聊的吗？",
    "visual_context": "无法可靠判断用户是否在场",
    "total_latency_ms": 45,
    "playback_completed": true,
    "playback_interrupted": false,
    "reply_source": "local_vtuber"
  }
]
```

---

### GET /api/session/history?limit=10

**Response** `200`:
```json
{
  "history": "User: 你好\nAI: 晚上好！我是澪，有什么想聊的吗？"
}
```

---

### GET /api/consent

**Response** `200`:
```json
{
  "camera": false,
  "microphone": false,
  "external_vision": false,
  "save_summary": false,
  "save_observation": false
}
```

---

### POST /api/consent/{item}/grant

**Path params**: `item` = `camera` | `microphone` | `external_vision`

**Response** `200`:
```json
{"status": "granted", "item": "camera"}
```

**Error** `400`:
```json
{"error": "Unknown consent item: xxx"}
```

---

### POST /api/consent/{item}/revoke

同 grant，返回 `{"status": "revoked", "item": "..."}`。

---

### POST /api/consent/revoke-all

**Response** `200`:
```json
{"status": "all_revoked"}
```

---

### GET /api/consent/audit?limit=50

**Response** `200`:
```json
[
  {"timestamp": "2024-06-10T...", "item": "camera", "old_value": false, "new_value": true, "reason": "ws_client"}
]
```

---

### GET /api/camera/metrics

**Response** `200`:
```json
{"state": "active", "frames_received": 120, "frames_dropped": 0, "avg_fps": 0.5, "uptime_sec": 60.0, "errors": 0}
```

---

### GET /api/audio/metrics

**Response** `200`:
```json
{"state": "listening", "chunks_received": 300, "total_duration_ms": 60000, "speech_segments": 5, "uptime_sec": 60.0, "errors": 0}
```

---

### GET /api/vision/usage

**Response** `200`:
```json
{"enabled": false, "provider": "noop", "frames_this_minute": 0, "max_frames_per_minute": 6, "cost_this_hour": 0.0, "total_frames": 0, "total_cost": 0.0, "analyze_count": 0, "error_count": 0}
```

---

## WebSocket API

连接: `ws://127.0.0.1:8001/ws`

### 客户端 → 服务端

#### ping (心跳)
```json
{"type": "ping"}
```
→ 回复 `{"type": "pong", "timestamp": 1718000000.0}`

#### frame (发送视频帧)
```json
{
  "type": "frame",
  "data": "<base64 JPEG>",
  "width": 640,
  "height": 480,
  "format": "jpeg"
}
```
→ 回复 `{"type": "observation", "data": {...}}`

#### speech_input (发送语音)
```json
{
  "type": "speech_input",
  "data": "<base64 audio>",
  "duration_ms": 2000,
  "sample_rate": 16000,
  "vad_ended": true,
  "vad_text": "",
  "confidence": 0
}
```
→ 回复 `{"type": "ai_response", ...}` 或 `{"type": "system_error", ...}`

#### text_input (发送文字)
```json
{"type": "text_input", "text": "你好"}
```
→ 回复 `{"type": "ai_response", ...}`

#### interrupt (打断)
```json
{"type": "interrupt"}
```
→ 回复 `{"type": "interrupted"}`

#### consent_update (授权变更)
```json
{"type": "consent_update", "item": "camera", "granted": true}
```
→ 回复 `{"type": "consent_changed", "item": "camera", "granted": true, "state": {...}}`

#### get_status (请求状态)
```json
{"type": "get_status"}
```
→ 回复 `{"type": "status", "data": {...}}`

---

### 服务端 → 客户端

#### status

连接后第一条消息即为 status。

```json
{
  "type": "status",
  "data": {
    "service": "Video Companion",
    "version": "0.3.0-dev",
    "project_mode": "standalone_ai_vtuber",
    "session_state": "idle",
    "consent": {"camera": false, "microphone": false, "external_vision": false},
    "...": "..."
  }
}
```

#### observation

每帧画面检测后推送。

```json
{
  "type": "observation",
  "data": {
    "timestamp": 1718000000.0,
    "user_present": null,
    "presence_status": "unknown",
    "presence_confidence": 0.0,
    "detector_available": false,
    "camera_usable": true,
    "face": {"present": false, "count": 0, "confidence": 0.0, "rough_mood": "unknown"},
    "body": {"present": false, "count": 0},
    "motion": {"level": "still", "score": 0.0, "changed_regions": 0},
    "object_hint": null,
    "brightness": 0.5,
    "blur_score": 100.0,
    "is_usable": true,
    "external_analysis": false,
    "external_description": null
  }
}
```

所有字段保证存在，不会缺失。

#### ai_response

每轮对话后推送。**主项目最核心的消息**。

```json
{
  "type": "ai_response",
  "turn_id": 1,
  "text": "你好呀。",
  "audio_base64": "",
  "audio_format": "mp3",
  "total_latency_ms": 120,
  "visual_context": "无法可靠判断用户是否在场",
  "asr_source": "text_input",
  "reply_source": "local_vtuber",
  "avatar_state": {
    "expression": "talking",
    "mouth_open": true,
    "speaking": true,
    "looking_at_user": false,
    "attention": "unknown",
    "emotion": "calm",
    "expression_confidence": 0.5,
    "blink_requested": false,
    "idle_animation": "idle_01"
  }
}
```

**字段保证**：
- `text` 字符串，永不为 None
- `audio_base64` 字符串（TTS 成功时有内容，失败/无 TTS 时为空字符串 `""`）
- `avatar_state` 对象，字段完整
- `reply_source` 为 `"local_vtuber"` 或 `"legacy_bridge"`
- `turn_id` 从 1 开始递增

#### transcript

每轮对话记录。

```json
{"type": "transcript", "turn_id": 1, "speaker": "user", "text": "你好"}
{"type": "transcript", "turn_id": 1, "speaker": "ai", "text": "你好呀。"}
```

`speaker` 值为 `"user"` 或 `"ai"`。

#### system_error

错误通知。

```json
{
  "type": "system_error",
  "code": "asr_failed",
  "message": "语音识别失败：ASR 服务不可用"
}
```

错误码完整列表见 [ERROR_CODES.md](./ERROR_CODES.md)。

#### consent_changed

```json
{
  "type": "consent_changed",
  "item": "camera",
  "granted": true,
  "state": {"camera": true, "microphone": false, "external_vision": false, "save_summary": false, "save_observation": false}
}
```

#### interrupted

```json
{"type": "interrupted"}
```

---

## Legacy Bridge (可选)

video-companion 默认以 standalone AI VTuber 模式运行。

旧版 Project Mnemosyne 桥接详见 [docs/LEGACY_BRIDGE.md](./docs/LEGACY_BRIDGE.md)。
仅在 `legacy_bridge.enabled: true` 时激活，不影响主路径。
