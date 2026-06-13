# Video Companion — 交接文档 (HANDOFF.md)

> 供其他 AI/开发者接手本项目时使用。
> 本文档描述已完成的工作、每个模块的功能、测试状态、已知限制和后续建议。

---

## 项目概览

**Video Companion** 是一个实时视频陪伴独立 Web 服务。用户打开浏览器后，AI 基于摄像头画面、语音输入和人格上下文进行多模态对话。

| 属性 | 值 |
| --- | --- |
| 项目路径 | `E:\视觉\video-companion\` |
| 语言 | Python 3.14 (后端) + Vanilla JS (前端) |
| Web 框架 | FastAPI + Uvicorn |
| 实时通信 | WebSocket |
| 测试覆盖 | 8 模块 / 68 测试 / 全部通过 |
| 当前版本 | 0.8.0 |

---

## 目录结构

```
video-companion/
  README.md                          # 项目说明
  config.example.yaml                # 配置模板
  requirements.txt                   # 依赖
  run_tests.py                       # 测试入口
  app/
    __init__.py                      # 包标识
    server.py                        # [核心] FastAPI 主服务 + WebSocket 消息分发
    consent.py                       # [V7] 用户授权管理 + 审计日志
    media_session.py                 # [V5] 会话状态机 + 多模态对话循环 + DialogueEngine
    camera_source.py                 # [V2] 摄像头采集抽象 + 帧缓冲 + 指标
    audio_source.py                  # [V4] 麦克风抽象 + VAD 检测 + 缓冲管理
    local_vision.py                  # [V2] 本地视觉检测 (OpenCV / 回退模式)
    vision_provider.py               # [V3] 外部视觉模型 (Provider 模式 + 频控)
    speech_provider.py               # [V4] ASR/TTS Provider (Whisper / TTS / Edge)
    mnemosyne_client.py              # [V6] 主项目 HTTP API 客户端
  web/
    index.html                       # [V8] 会话页面
    app.js                           # [V8] 前端逻辑
    style.css                        # [V8] 深色主题样式
  tests/
    __init__.py
    test_consent.py                  # 8 tests
    test_camera_source.py            # 8 tests
    test_audio_source.py             # 8 tests
    test_local_vision.py             # 8 tests
    test_vision_provider.py          # 9 tests
    test_speech_provider.py          # 10 tests
    test_media_session.py            # 9 tests
    test_mnemosyne_client.py         # 8 tests
```

---

## 模块功能说明

### 1. `app/server.py` — 主服务入口

**功能**：FastAPI 应用创建、WebSocket 消息路由、REST API 端点。

**API 端点**：
| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 返回前端页面或 JSON |
| GET | `/api/status` | 系统全状态 |
| GET | `/api/health` | 健康检查 |
| GET/POST | `/api/consent/*` | 授权管理 |
| POST | `/api/session/start` | 启动视频会话 |
| POST | `/api/session/stop` | 停止视频会话 |
| GET | `/api/session/status` | 会话状态 |
| GET | `/api/session/turns` | 对话轮次列表 |
| GET | `/api/session/history` | 对话历史 |
| GET | `/api/camera/metrics` | 摄像头指标 |
| GET | `/api/audio/metrics` | 音频指标 |
| GET | `/api/vision/usage` | 视觉模型用量 |
| WS | `/ws` | WebSocket 实时通信 |

**WebSocket 消息类型**：
| 发送方向 | Type | 说明 |
| --- | --- | --- |
| 前端→后端 | `frame` | 视频帧 (base64 JPEG) |
| 前端→后端 | `speech_input` | 语音数据 + VAD |
| 前端→后端 | `text_input` | 文本输入回退 |
| 前端→后端 | `interrupt` | 打断播放 |
| 前端→后端 | `consent_update` | 授权变更 |
| 后端→前端 | `observation` | 画面观察结果 |
| 后端→前端 | `ai_response` | AI 回复 + TTS 音频 |
| 后端→前端 | `transcript` | 对话记录 |
| 后端→前端 | `interrupted` | 打断确认 |
| 后端→前端 | `status` | 状态同步 |

### 2. `app/consent.py` — 授权管理

**功能**：
- 分项独立授权 (camera / microphone / external_vision / save_summary / save_observation)
- 默认全部关闭
- 审计日志 (内存 + 文件持久化)
- 授权变更回调
- PII 脱敏日志
- 隐私安全状态检查 (`is_privacy_safe()`)

**关键类**：`ConsentManager`, `ConsentState`, `ConsentItem`

### 3. `app/media_session.py` — 会话管理

**功能**：
- 会话状态机: IDLE → CONNECTING → ACTIVE → PAUSED → ENDING → ENDED
- VideoTurn: 多模态对话轮次数据结构
- DialogueEngine: 回复生成引擎 (LLM 优先 → 模板回退)
- PersonaContext: 人格上下文 (风格/关系/边界)
- 对话历史管理
- 视觉上下文构建
- 会话摘要生成
- 延迟统计 (avg/max/min)

**关键类**：`MediaSession`, `VideoTurn`, `DialogueEngine`, `PersonaContext`, `SessionStats`

### 4. `app/camera_source.py` — 摄像头采集

**功能**：
- 帧接收和缓冲 (deque, 可配置大小)
- 帧指标 (FPS, dropped, received)
- 状态管理 (OFF/STARTING/ACTIVE/ERROR)
- 错误处理

**关键类**：`CameraSource`, `CameraFrame`, `CameraMetrics`

### 5. `app/audio_source.py` — 音频采集

**功能**：
- 音频块接收和缓冲
- SimpleVAD: 简易语音活动检测 (能量阈值 + 静音区间)
- 缓冲时长限制 (max_audio_buffer_sec)
- VAD 说话/静音事件回调
- 中断处理

**关键类**：`AudioSource`, `AudioChunk`, `SimpleVAD`, `AudioMetrics`

### 6. `app/local_vision.py` — 本地视觉检测

**功能**：
- VideoObservation: 标准化画面观察数据结构
- 人脸检测 (OpenCV Haar Cascade, 有回退)
- 动作检测 (帧差法)
- 亮度/模糊度评估
- 无 OpenCV 时纯 Python 回退

**关键类**：`LocalVisionDetector`, `VideoObservation`, `FaceDetection`, `MotionDetection`
**枚举**：`MoodLabel` (neutral/happy/sad/surprised/focused/confused/unknown), `MotionLabel` (still/slight/moderate/active)

### 7. `app/vision_provider.py` — 外部视觉模型

**功能**：
- Provider 模式: Mock / OpenAI GPT-4o / Anthropic Claude
- RateLimiter: 分钟频率限制 + 小时/日费用上限
- 降级策略: skip / local_only
- 费用估算 (基于 token 用量)
- 安全内容检查 (`_check_safe_content`)

**关键类**：`VisionProviderManager`, `RateLimiter`, `OpenAIVisionProvider`, `AnthropicVisionProvider`, `MockVisionProvider`

### 8. `app/speech_provider.py` — 语音服务

**功能**：
- ASR Provider: Mock / OpenAI Whisper / Noop
- TTS Provider: Mock / OpenAI TTS / Edge TTS (免费回退)
- 流式 TTS
- 中断机制
- 语音状态机

**关键类**：`SpeechProviderManager`, `OpenAWhisperASR`, `OpenAITTSProvider`, `EdgeTTSProvider`

### 9. `app/mnemosyne_client.py` — 主项目桥接

**功能**：
- 获取会话上下文 (GET /api/video/session-context)
- 回写会话摘要 (POST /api/video/session-summary)
- 回写视觉观察 (POST /api/video/observation)
- 同步授权状态 (POST /api/video/consent)
- 离线模式回退 (主项目不可达时仍可用)
- 自动重试

**关键类**：`MnemosyneClient`, `SessionContext`, `SessionSummaryPayload`

### 10. `web/app.js` — 前端逻辑

**功能**：
- WebSocket 实时连接 + 自动重连
- 摄像头 getUserMedia 采集 + 每 2 秒抽帧发送
- 麦克风 Web Audio API 采集 + VAD + MediaRecorder
- 语音播放 (base64 解码 + HTML Audio)
- 视觉可视化 (音频条动画)
- 授权开关 + 后端同步
- 会话控制 (开始/停止/打断)
- 对话日志
- 3 秒轮询状态同步

### 11. `web/style.css` — 样式

深色主题，响应式布局 (桌面 2 列 / 移动 1 列)，自定义滚动条，动画过渡。

---

## 测试状态

**总计**: 68 tests, 68 passed, 0 failed

| 模块 | 测试数 | 状态 | 覆盖重点 |
| --- | --- | --- | --- |
| test_consent | 8 | OK | 默认关闭、单项/批量授权、审计日志、序列化 |
| test_camera_source | 8 | OK | 帧接收、缓冲、指标、状态、丢弃 |
| test_audio_source | 8 | OK | 音频接收、VAD、缓冲管理、VAD转换 |
| test_local_vision | 8 | OK | 初始化、空帧、回退、数据结构、摘要 |
| test_vision_provider | 9 | OK | Mock、频限、Provider切换、序列化 |
| test_speech_provider | 10 | OK | Mock ASR/TTS、流式、中断、空文本 |
| test_media_session | 9 | OK | 状态机、Turn、对话引擎、暂停恢复 |
| test_mnemosyne_client | 8 | OK | 离线回退、数据结构、序列化 |

运行测试: `python run_tests.py`

---

## 已知限制与待修复

### 无需立即修复（设计如此）

| 限制 | 说明 | 影响 |
| --- | --- | --- |
| 无 WebRTC | 未实现 WebRTC 实时视频流 | 抽帧模式有 2 秒延迟，V9+ 可升级 |
| 本地视觉检测无 OpenCV 时用回退 | 回退模式保守假设用户在场 | 人脸计数/情绪检测不可用 |
| SimpleVAD 基于能量阈值 | 不如 Silero/WebRTC VAD 准确 | 噪音环境可能误判 |
| 对话引擎模板回退 | 无 LLM 时使用简单模板 | 回复质量受限 |
| 无实际数据库 | 数据仅内存存储 | 重启丢失 |
| 无用户认证 | 单用户本地模式 | 不适合多用户部署 |
| Edge TTS 需额外安装 | `pip install edge-tts` | 可选依赖 |
| 浏览器 SpeechRecognition 不可靠 | 用 Web Speech API 做本地 VAD | 建议用后端 ASR |

### 已知 Bug (无)

当前 68 测试全通过，无已知 Bug。

### 未完成的功能（按计划应跳过）

| 功能 | 原因 |
| --- | --- |
| 完整 WebRTC 视频流 | V1-V8 用抽帧模式，WebRTC 是 V9+ |
| Live2D/形象驱动 | 解耦设计，另起模块 |
| 长期记忆写入 | 主权在 Mnemosyne，本项目只提交候选 |
| OCR/屏幕理解 | 不在本项目范围 |

---

## 如何启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制配置
cp config.example.yaml config.yaml
# 编辑 config.yaml 配置 API keys

# 3. 运行测试
python run_tests.py

# 4. 启动服务
python -m app.server
# 或
python -c "import asyncio; from app.server import main; asyncio.run(main())"

# 5. 打开浏览器
# http://localhost:8001
```

---

## 与其他 AI 对接要点

### 如果你想扩展本项目：

1. **添加新的 Vision Provider**: 继承 `BaseVisionProvider`，在 `PROVIDER_REGISTRY` 注册
2. **添加新的 ASR/TTS Provider**: 继承 `BaseASRProvider` / `BaseTTSProvider`，在对应的 REGISTRY 注册
3. **改进对话引擎**: `DialogueEngine._llm_generate()` 替换为你的 LLM 调用
4. **改进 VAD**: 替换 `SimpleVAD` 为 Silero VAD 或 WebRTC VAD
5. **添加 WebRTC**: `app/webrtc_handler.py` 新建模块，`server.py` 添加新路由

### 接口契约 (与主项目):

| 你需要实现 | 方法 | 路径 |
| --- | --- | --- |
| 提供会话上下文 | GET | `/api/video/session-context?persona_id=...` |
| 接收会话摘要 | POST | `/api/video/session-summary` |
| 接收视觉观察 | POST | `/api/video/observation` |
| 接收授权同步 | POST | `/api/video/consent` |

### 关键数据结构:

```python
# VideoObservation (核心输出)
{
    "timestamp": float,
    "user_present": bool,
    "face": {"present": bool, "rough_mood": str, "confidence": float},
    "motion": {"level": str, "score": float},
    "object_hint": str | None,
    "external_analysis": bool,
    "external_description": str | None,
}

# VideoTurn (对话轮次)
{
    "turn_id": int,
    "user_text": str,
    "ai_response": str,
    "visual_context": str,
    "total_latency_ms": int,
}

# Consent State (授权)
{
    "camera": bool,
    "microphone": bool,
    "external_vision_upload": bool,
    "save_summary": bool,
    "save_observation": bool,
}
```

---

## 配置关键项

```yaml
# vision_provider - 外部视觉模型
vision_provider:
  provider: mock          # mock | openai | anthropic
  max_frames_per_minute: 6
  max_cost_per_hour: 0.5
  fallback_on_limit: skip # skip | local_only

# speech - 语音
speech:
  asr:
    provider: mock        # mock | openai_whisper
  tts:
    provider: mock        # mock | openai_tts | edge_tts

# mnemosyne - 主项目
mnemosyne:
  enabled: true           # 设为 false 完全离线运行
  api_base: "http://127.0.0.1:8000"

# privacy - 隐私 (所有默认 false)
privacy:
  defaults:
    camera: false
    microphone: false
    external_vision: false
```

---

## 版本历史

| 版本 | 内容 | 状态 |
| --- | --- | --- |
| V0 | 技术预研 | 完成 |
| V1 | 本地视频会话壳 | REST API + WebSocket 框架 |
| V2 | 抽帧与本地感知 | OpenCV 人脸/动作检测 + VideoObservation |
| V3 | 视觉模型接口 | OpenAI GPT-4o / Anthropic Claude + 频控 + 费用估算 |
| V4 | 语音输入输出 | OpenAI Whisper ASR + OpenAI TTS + ElevenLabs (备选) |
| V5 | 多模态对话循环 | GPT-4o-mini DialogueEngine + VideoTurn 管线 |
| V6 | 主项目桥接 | MnemosyneClient + 离线回退 |
| V7 | 隐私和成本硬化 | 审计日志 + 分项授权 + 画面安全检查 |
| V8 | 体验打磨 | 完整前端 + 抽帧调度 + 打断 + 重连 |

## 生产级 Provider 状态

| Provider | 类型 | 状态 | 需要 |
| --- | --- | --- | --- |
| OpenAI Whisper | ASR | **已就绪** | OPENAI_API_KEY |
| OpenAI TTS (tts-1) | TTS | **已就绪** | OPENAI_API_KEY |
| ElevenLabs | TTS | 可选 | ELEVENLABS_API_KEY |
| OpenAI GPT-4o | 视觉 | 就绪（默认关闭） | OPENAI_API_KEY |
| Anthropic Claude | 视觉 | 可选 | ANTHROPIC_API_KEY |
| OpenCV Haar Cascade | 人脸检测 | **已就绪** | opencv-python |
| GPT-4o-mini | 对话引擎 | **已就绪** | OPENAI_API_KEY |

---

*生成时间: 2026-06-13*
*测试结果: 68/68 passed*
