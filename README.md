# Video Companion

AI VTuber 项目的实时感知与互动核心。

它可以独立运行，不依赖 Project Mnemosyne / 忆界树。

当前目标是完成一个本地可运行的 AI VTuber 基础闭环：
用户打开网页 → 授权摄像头/麦克风 → 摄像头抽帧 → 本地视觉观察 → 语音输入 → ASR → 本地角色回复 → TTS → 前端播放和显示 → 会话结束生成摘要。

未来可以继续接 Live2D、虚拟形象动作、表情控制、OBS / 直播软件、桌面陪伴模式。

---

## 当前真实状态

| 阶段 | 名称 | 状态 |
| --- | --- | --- |
| 基础闭环 | 本地 AI VTuber 对话 | 可用 — REST API + WebSocket + LocalVTuberEngine |
| 视觉 | 抽帧与本地感知 | 可用 — OpenCV 检测就绪，fallback 不编造结果 |
| 视觉 | 外部视觉模型接口 | 骨架可用 — Provider 可替换，默认关闭 |
| 语音 | 语音输入输出 | 骨架可用 — ASR/TTS mock 默认可用，真实 provider 需配 key |
| 会话 | 会话摘要 | 可用 — 规则生成，无需数据库 |
| 形象 | Live2D/VTuber 状态接口 | 已预留 — avatar_state 输出就绪，不驱动真实 Live2D |
| 隐私 | 隐私和授权硬化 | 可用 — 分项授权、审计日志、默认全关 |
| 体验 | UI 打磨 | 部分完成 |
| 外部 | Legacy Bridge | 可选 — 默认关闭，仅供历史兼容 |

---

## 当前未完成

| 功能 | 状态 |
| --- | --- |
| 完整 WebRTC 视频流 | 未开始 — 当前用抽帧模式 |
| Live2D / VRM 真实驱动 | 未开始 — 状态接口已预留 |
| 复杂长期记忆数据库 | 不在当前阶段范围 |
| 用户账号体系 | 不在当前阶段范围 |
| 社交平台自动运营 | 不在当前阶段范围 |
| 接 OBS / 直播软件 | 未开始 |
| 桌面陪伴模式 | 未开始 |

---

## 快速开始

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
python run_tests.py          # 运行测试
python -m app.server         # 启动服务 → http://localhost:8001
```

---

## 目录

```
video-companion/
  README.md
  HANDOFF.md                  # 交接文档
  API_CONTRACT.md             # Legacy bridge 接口契约
  config.example.yaml
  requirements.txt
  run_tests.py
  app/
    server.py                 # FastAPI 主服务 + WebSocket
    consent.py                # 授权管理 + 审计
    media_session.py          # 会话状态机 + LocalVTuberEngine
    camera_source.py          # 摄像头采集抽象
    audio_source.py           # 麦克风 + VAD + 音频缓冲
    local_vision.py           # OpenCV 人脸/动作检测
    vision_provider.py        # 外部视觉模型 Provider
    speech_provider.py        # OpenAI Whisper ASR + TTS
    mnemosyne_client.py       # Legacy bridge (可选，默认关闭)
    avatar_state.py           # Live2D/VTuber 状态输出预留
  web/
    index.html / app.js / style.css
  scripts/
    verify_camera.py / verify_vision_provider.py / verify_mnemosyne_bridge.py
  tests/
    10 模块
```

---

## 配置说明

项目默认运行在 `standalone_ai_vtuber` 模式。

关键配置项（`config.example.yaml`）：

```yaml
project:
  mode: "standalone_ai_vtuber"

legacy_bridge:
  enabled: false            # 历史 Mnemosyne 桥接，默认关闭

persona:
  name: "Mio"
  display_name: "澪"
  language: "zh"
  style: "自然、简短、温和、稍微冷静"
  max_reply_chars: 100
  allow_visual_comment: true
  avoid_fake_memory: true
```

ASR/TTS 默认使用 mock provider。真实语音需要配置 API key 并修改 `speech.asr.provider` 和 `speech.tts.provider`。

---

## 隐私说明

- 摄像头、麦克风、外部视觉模型默认关闭
- 需用户分别明确授权
- 不保存原始视频帧和音频 (`save_raw_media: false`)
- 授权变更全部审计可追溯
- 视觉 unknown 状态下不编造观察

---

## 未来路线

| 优先级 | 方向 | 说明 |
| --- | --- | --- |
| 高 | 更自然 TTS | 接入 Edge TTS 或本地语音合成 |
| 高 | 外部 LLM 可选接入 | 让 LocalVTuberEngine 可选调用外部大模型 |
| 中 | Live2D 状态层 | 根据 avatar_state 驱动 Live2D/VRM |
| 中 | OBS / 桌面陪伴 | 绿幕输出、桌面小窗模式 |
| 低 | 更稳定视觉理解 | 提升 face detection、物品识别 |
| 低 | 外部记忆系统对接 | 可选接入长期记忆，非默认依赖 |

---

## 它不是什么

- 不是 Project Mnemosyne / 忆界树 的子模块
- 不是必须依赖外部人格系统的客户端
- 不是长期记忆数据库
- 不是多 Agent 系统
- 不是社交平台运营工具

它是一个独立可运行的 AI VTuber 实时感知与互动核心。
