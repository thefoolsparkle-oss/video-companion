# Error Codes

video-companion 统一错误码规范，主项目接入时以此为准。

---

## WebSocket 错误 (type: system_error)

| Code | 含义 | 触发条件 | 前端行为 | 可重试 |
| --- | --- | --- | --- | --- |
| `asr_no_audio` | 未收到有效音频 | 用户说完话但缓冲区无音频数据 | 提示用户重新说话 | 是 |
| `asr_failed` | 语音识别失败 | ASR 服务返回错误或不可用 | 显示"语音识别失败"，降级到文字输入 | 是 |
| `no_session` | 无活动会话 | 未 start_session 就发送语音/文字 | 提示"请先开始会话" | 是（先启动） |
| `turn_failed` | 对话轮次处理失败 | LocalVTuberEngine 或 TTS 异常 | 显示错误，建议重试 | 是 |
| `invalid_json` | 无效 JSON | 前端发送了不合法的 JSON | 忽略并等待后续消息 | 是 |
| `unknown_message_type` | 未知消息类型 | 前端发了未定义的 type | 忽略 | 否 |
| `consent_required` | 需要用户授权 | 操作需要摄像头/麦克风但未授权 | 引导用户到授权面板 | 否 |
| `camera_unavailable` | 摄像头不可用 | getUserMedia 失败 | 提示用户检查摄像头权限 | 是 |
| `microphone_unavailable` | 麦克风不可用 | getUserMedia 失败 | 提示用户检查麦克风权限 | 是 |
| `vision_provider_unavailable` | 外部视觉模型不可用 | API key 缺失或服务不可达 | 静默降级到本地检测 | 否 |
| `tts_failed` | 语音合成失败 | TTS 服务错误 | 仍显示文字回复，不播放语音 | 否 |

---

## ASR / TTS 失败行为

- **ASR 失败** (`asr_no_audio` / `asr_failed`) → 不进入 LocalVTuberEngine，不生成角色回复
- **TTS 失败** → 仍返回 `ai_response.text`，但 `audio_base64` 为空字符串
  - 角色不会说"系统错误"
  - 前端应检查 `audio_base64` 长度决定是否播放

---

## 主项目接入建议

收到 `system_error` 时：
1. 根据 `code` 查上表
2. 记录日志
3. 根据"前端行为"列决定 UI 展示
4. 可重试的错，给用户重试按钮
5. 不可重试的错，静默处理或引导
