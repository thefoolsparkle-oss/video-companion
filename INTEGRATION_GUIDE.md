# Integration Guide — AI VTuber 主项目接入指南

video-companion 是 AI VTuber 主项目的实时感知与互动核心模块。
主项目通过 REST API 和 WebSocket 接入它。

---

## 1. video-companion 是什么

一个独立运行的 Web 服务，提供：

- 摄像头帧接收 (前端 getUserMedia → WebSocket frame → 后端处理)
- 麦克风输入 (Web Audio API → WebSocket speech_input → 后端 VAD + ASR)
- 本地视觉观察 (OpenCV 人脸/动作检测)
- 外部视觉模型调用 (需授权，默认关闭)
- ASR 语音识别 (mock / openai_whisper)
- TTS 语音合成 (mock / openai_tts / edge_tts)
- 本地角色对话 (LocalVTuberEngine)
- avatar_state 输出 (供 Live2D / 虚拟形象层使用)
- 会话状态管理 + 摘要
- 隐私 / 授权控制

---

## 2. 主项目什么时候启动它

- 用户点击"进入视频会话"时
- 用户需要摄像头 + 语音交互时
- 用户需要角色根据视觉画面自然回应时

主项目启动 video-companion 作为子进程或独立服务即可。

---

## 3. 启动服务

```bash
cd video-companion
pip install -r requirements.txt
cp config.example.yaml config.yaml
python -m app.server
```

默认监听 `http://127.0.0.1:8001`。

验证启动成功：

```bash
curl http://127.0.0.1:8001/api/health
# → {"status": "ok"}
```

---

## 4. REST API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/status` | 系统全状态 |
| POST | `/api/session/start?persona_id=default` | 启动会话 |
| POST | `/api/session/stop` | 停止会话 |
| GET | `/api/session/status` | 会话状态 |
| GET | `/api/session/turns` | 对话轮次 |
| GET | `/api/session/history` | 对话历史文本 |
| GET | `/api/consent` | 授权状态 |
| POST | `/api/consent/{item}/grant` | 授权 (item=camera/microphone/external_vision) |
| POST | `/api/consent/{item}/revoke` | 撤销授权 |
| POST | `/api/consent/revoke-all` | 全部撤销 |
| GET | `/api/consent/audit` | 审计日志 |
| GET | `/api/camera/metrics` | 摄像头指标 |
| GET | `/api/audio/metrics` | 音频指标 |
| GET | `/api/vision/usage` | 视觉模型用量 |

详见 [API_CONTRACT.md](./API_CONTRACT.md)。

---

## 5. WebSocket (`/ws`)

主项目通过 WebSocket 与 video-companion 实时通信。

### 主项目 → video-companion

| type | 关键字段 | 说明 |
| --- | --- | --- |
| `ping` | — | 心跳 |
| `frame` | `data`(base64), `width`, `height`, `format` | 发送视频帧 |
| `speech_input` | `data`(base64), `vad_ended`, `vad_text` | 发送语音数据 |
| `text_input` | `text` | 发送文字输入 |
| `interrupt` | — | 打断播放 |
| `consent_update` | `item`, `granted` | 授权变更 |
| `get_status` | — | 请求当前状态 |

### video-companion → 主项目

| type | 关键字段 | 说明 |
| --- | --- | --- |
| `status` | `data` | 系统状态 |
| `observation` | `data`, `external`(可选) | 画面观察 |
| `ai_response` | `text`, `audio_base64`, `avatar_state`, `reply_source` | AI 回复 + 语音 + 形象状态 |
| `transcript` | `speaker`, `text`, `turn_id` | 对话记录 |
| `system_error` | `code`, `message` | 系统错误 (见 ERROR_CODES.md) |
| `consent_changed` | `item`, `granted`, `state` | 授权变更通知 |
| `interrupted` | — | 打断确认 |

---

## 6. 典型调用流程

```
1. GET /api/health
2. POST /api/session/start?persona_id=default
3. WebSocket connect → /ws
4. 收到 status (含 consent 全关)
5. 前端授权 camera + microphone → consent_update
6. 前端 getUserMedia → frame (每2秒) + speech_input (每次说话)
7. 收到 observation (每帧检测结果)
8. 收到 ai_response (含 avatar_state, audio_base64)
9. 前端播放 audio_base64, 更新 avatar_state
10. POST /api/session/stop
11. 获取 summary
```

---

## 7. 权限

video-companion 所有敏感项默认关闭：

```json
{"camera": false, "microphone": false, "external_vision": false}
```

主项目需要引导用户逐一授权。
授权变更通过 WebSocket `consent_update` 同步到后端。

---

## 8. Session Summary

`POST /api/session/stop` 返回：

```json
{
  "status": "stopped",
  "summary": {
    "session_id": "vc-session-...",
    "persona_name": "Mio",
    "display_name": "澪",
    "duration_sec": 45.2,
    "total_turns": 3,
    "summary_text": "本次会话用户说了：你好、今天天气不错、再见。",
    "key_topics": ["问候", "天气"],
    "visual_notes": [],
    "system_notes": ["standalone_ai_vtuber_mode"],
    "saved_locally": false
  }
}
```

主项目可以保存 `summary_text` 作为本次会话记录。

---

## 9. 替换 Provider

### ASR

修改 `config.yaml`:

```yaml
speech:
  asr:
    provider: openai_whisper
```

设置环境变量 `OPENAI_API_KEY`。

### TTS

```yaml
speech:
  tts:
    provider: openai_tts      # or edge_tts
```

### 外部视觉模型

```yaml
vision_provider:
  default_on: false            # 需用户授权后才开启
  provider: openai             # or anthropic
```

---

## 10. 接 Live2D / 虚拟形象

video-companion 输出 `avatar_state` 但不驱动任何形象 SDK。

主项目从 `ai_response.avatar_state` 读取：

```json
{
  "expression": "talking",
  "mouth_open": true,
  "speaking": true,
  "looking_at_user": true,
  "attention": "user_present",
  "emotion": "calm",
  "blink_requested": false,
  "idle_animation": "idle_01"
}
```

然后映射到你的 Live2D/VRM 参数：

| avatar_state 字段 | Live2D 参数示例 |
| --- | --- |
| `mouth_open` | `ParamMouthOpenY` |
| `expression` | `ParamExpression` / 表情切换 |
| `looking_at_user` | 眼球跟踪目标 |
| `speaking` | 是否播放口型动画 |

---

## 11. 配置

完整配置见 `config.example.yaml`。
默认 `project.mode: standalone_ai_vtuber`，`legacy_bridge.enabled: false`。

---

## 12. 示例

- [Python REST 客户端](examples/main_project_client.py)
- [Python WebSocket 客户端](examples/main_project_websocket_client.py)
- [前端集成示例](examples/simple_frontend_integration.html)
- [独立验证脚本](scripts/verify_standalone.py)
