# Video Companion — 交接文档 (HANDOFF.md)

> 供其他 AI/开发者接手本项目时使用。
> 本文档描述已完成的工作、每个模块的功能、测试状态、已知限制和后续建议。

---

## 项目定位

**Video Companion** 是 AI VTuber 项目的独立实时感知与互动核心。

它可以独立运行，不依赖 Project Mnemosyne / 忆界树。

| 属性 | 值 |
| --- | --- |
| 项目路径 | `E:\视觉\video-companion\` |
| 语言 | Python 3.14 (后端) + Vanilla JS (前端) |
| Web 框架 | FastAPI + Uvicorn |
| 实时通信 | WebSocket |
| 运行模式 | standalone_ai_vtuber |
| 当前版本 | 0.3.0-dev |

---

## 目录结构

```
video-companion/
  README.md                          # 项目说明（AI VTuber 定位）
  config.example.yaml                # 配置模板（standalone 默认）
  requirements.txt                   # 依赖
  run_tests.py                       # 测试入口
  app/
    __init__.py                      # 包标识
    server.py                        # [核心] FastAPI 主服务 + WebSocket 消息分发
    consent.py                       # 用户授权管理 + 审计日志
    media_session.py                 # 会话状态机 + LocalVTuberEngine 本地对话引擎
    camera_source.py                 # 摄像头采集抽象 + 帧缓冲 + 指标
    audio_source.py                  # 麦克风抽象 + VAD 检测 + 缓冲管理
    local_vision.py                  # 本地视觉检测 (OpenCV / 回退模式)
    vision_provider.py               # 外部视觉模型 (Provider 模式 + 频控)
    speech_provider.py               # ASR/TTS Provider (Whisper / TTS / Edge)
    mnemosyne_client.py              # Legacy bridge (历史兼容，默认关闭)
    avatar_state.py                  # Live2D/VTuber 状态输出预留
  web/
    index.html                       # 会话页面
    app.js                           # 前端逻辑
    style.css                        # 深色主题样式
  tests/
    __init__.py
    test_consent.py                  # 8 tests
    test_camera_source.py            # 8 tests
    test_audio_source.py             # 8 tests
    test_local_vision.py             # 8 tests
    test_vision_provider.py          # 9 tests
    test_speech_provider.py          # 10 tests
    test_media_session.py            # 13 tests (含 standalone 模式测试)
    test_mnemosyne_client.py         # 8 tests
    test_rest_api.py                 # 10 tests
    test_video_turn_contract.py      # 6 tests
```

---

## 模块功能说明

### 1. `app/server.py` — 主服务入口

**功能**：FastAPI 应用创建、WebSocket 消息路由、REST API 端点。
**运行模式**：默认 standalone_ai_vtuber，不依赖外部项目。

**API 端点**：
| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 返回前端页面或 JSON |
| GET | `/api/status` | 系统全状态（含 project_mode） |
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
| 前端→后端 | `text_input` | 文本输入 |
| 前端→后端 | `interrupt` | 打断播放 |
| 前端→后端 | `consent_update` | 授权变更 |
| 后端→前端 | `observation` | 画面观察结果 |
| 后端→前端 | `ai_response` | AI 回复 + TTS 音频 + avatar_state |
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

### 3. `app/media_session.py` — 会话管理 + LocalVTuberEngine

**功能**：
- 会话状态机: IDLE → CONNECTING → ACTIVE → PAUSED → ENDING → ENDED
- VideoTurn: 多模态对话轮次数据结构
- **LocalVTuberEngine**: 本地 AI VTuber 对话引擎（主路径）
  - 模板 + 规则型本地引擎
  - 结合视觉上下文回复
  - 不编造长期记忆
  - 视觉状态敏感（unknown/present/absent/unusable 分别对待）
- PersonaContext: 角色上下文 (name/Mio, display_name/澪, style)
- 对话历史管理
- 视觉上下文构建
- 会话摘要生成（规则生成，非空）
- Legacy bridge 覆写（可选，默认关闭）

**关键类**：`MediaSession`, `VideoTurn`, `LocalVTuberEngine`, `PersonaContext`, `SessionStats`

### 4-9. 其他模块

`camera_source.py`, `audio_source.py`, `local_vision.py`, `vision_provider.py`, `speech_provider.py` 功能与之前基本一致，详见各模块 docstring。

### 10. `app/mnemosyne_client.py` — Legacy Bridge

**功能**：历史 Project Mnemosyne API 客户端。默认关闭 (`legacy_bridge.enabled: false`)。
仅在配置中显式启用后才会尝试连接。

**关键类**：`MnemosyneClient`, `MnemosyneConfig`

### 11. `app/avatar_state.py` — 形象状态输出

**功能**：Live2D/VTuber 表现层预留接口。输出角色当前状态（表情、嘴型、说话、注意力等），不驱动真实 Live2D。

**关键类**：`AvatarState`, `Expression`, `Attention`

### 12. `web/app.js` — 前端逻辑

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
- avatar_state 显示

### 13. `web/style.css` — 样式

深色主题，响应式布局 (桌面 2 列 / 移动 1 列)，自定义滚动条，动画过渡。

---

## 测试状态

运行测试: `python run_tests.py`

| 模块 | 测试数 | 覆盖重点 |
| --- | --- | --- |
| test_consent | 8 | 默认关闭、单项/批量授权、审计日志、序列化 |
| test_camera_source | 8 | 帧接收、缓冲、指标、状态、丢弃 |
| test_audio_source | 8 | 音频接收、VAD、缓冲管理、VAD转换 |
| test_local_vision | 8 | 初始化、空帧、回退、数据结构、摘要 |
| test_vision_provider | 9 | Mock、频限、Provider切换、序列化 |
| test_speech_provider | 10 | Mock ASR/TTS、流式、中断、空文本 |
| test_media_session | 13 | 状态机、Turn、LocalVTuberEngine、standalone模式、视觉上下文、摘要 |
| test_mnemosyne_client | 8 | 离线回退、数据结构、序列化 |
| test_rest_api | 10 | 授权 REST 端点、revoke-all |
| test_video_turn_contract | 6 | 接口契约、长期内存写保护 |

---

## 已知限制与待修复

### 无需立即修复（设计如此）

| 限制 | 说明 | 影响 |
| --- | --- | --- |
| 无 WebRTC | 未实现 WebRTC 实时视频流 | 抽帧模式有 2 秒延迟 |
| 本地视觉检测无 OpenCV 时用回退 | 回退模式保守，返回 unknown | 人脸计数/情绪检测不可用 |
| SimpleVAD 基于能量阈值 | 不如 Silero/WebRTC VAD 准确 | 噪音环境可能误判 |
| LocalVTuberEngine 基于规则 | 无外部 LLM 时使用模板 | 回复质量受限，但比旧 offline_template 自然 |
| 无实际数据库 | 数据仅内存存储 | 重启丢失 |
| 无用户认证 | 单用户本地模式 | 不适合多用户部署 |

### 已知 Bug

无已知 Bug。

---

## 如何启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 复制配置
cp config.example.yaml config.yaml
# 编辑 config.yaml 配置 API keys（可选，不配置也能用 mock 运行）

# 3. 运行测试
python run_tests.py

# 4. 启动服务
python -m app.server
# http://localhost:8001
```

---

## 与其他 AI 对接要点

### 如果你想扩展本项目：

1. **添加新的 Vision Provider**: 继承 `BaseVisionProvider`，在 `PROVIDER_REGISTRY` 注册
2. **添加新的 ASR/TTS Provider**: 继承 `BaseASRProvider` / `BaseTTSProvider`，在对应的 REGISTRY 注册
3. **改进对话引擎**: `LocalVTuberEngine._template_generate()` 或替换为外部 LLM 调用
4. **改进 VAD**: 替换 `SimpleVAD` 为 Silero VAD 或 WebRTC VAD
5. **接入 Live2D**: 读取 `avatar_state` 输出来驱动 Live2D SDK
6. **接 OBS**: 将页面作为浏览器源添加到 OBS

### Legacy bridge 接口（仅在启用时使用）:

| 接口 | 方法 | 路径 |
| --- | --- | --- |
| 提供会话上下文 | GET | `/api/video/session-context?persona_id=...` |
| 接收会话摘要 | POST | `/api/video/session-summary` |
| 接收视觉观察 | POST | `/api/video/observation` |
| 接收授权同步 | POST | `/api/video/consent` |

---

## 配置关键项

```yaml
# project — 运行模式
project:
  mode: standalone_ai_vtuber

# legacy_bridge — 历史 Mnemosyne 桥接（默认关闭）
legacy_bridge:
  enabled: false

# persona — 角色
persona:
  name: "Mio"
  display_name: "澪"
  max_reply_chars: 100

# vision_provider - 外部视觉模型
vision_provider:
  default_on: false
  provider: mock          # mock | openai | anthropic

# speech - 语音
speech:
  asr:
    provider: mock        # mock | openai_whisper
  tts:
    provider: mock        # mock | openai_tts

# privacy - 隐私 (所有默认 false)
privacy:
  save_raw_media: false
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
| V3 | 视觉模型接口 | Provider 模式 + 频控 + 费用估算 |
| V4 | 语音输入输出 | ASR / TTS provider (mock + real) |
| V5 | 多模态对话循环 | LocalVTuberEngine + VideoTurn 管线 |
| V6 | Legacy bridge | MnemosyneClient + 可选回退 |
| V7 | 隐私和成本硬化 | 审计日志 + 分项授权 + 画面安全检查 |
| V8 | 体验打磨 (部分) | 完整前端 + 抽帧调度 + 打断 + 重连 |
| V0.3 | AI VTuber 重新定位 | standalone 模式、LocalVTuberEngine、avatar_state、session summary |

---

*生成时间: 2026-06-13*
