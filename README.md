# Video Companion

实时视频陪伴模块 — Project Mnemosyne 的"摄像头、麦克风、视频通话管道"。

**video-companion 不是独立 AI 伴侣产品，不是第二个人格系统，不是第二个记忆系统。**

它只负责：摄像头采集、麦克风输入、视频抽帧、本地视觉检测、外部视觉模型调用（需授权）、ASR 语音识别、TTS 语音播放、视频会话状态管理、授权隐私成本控制、与主项目 API 桥接。

它不负责：长期人格生成、长期记忆主权、核心聊天逻辑、用户账号体系、人格成长、关系变化。

## 当前真实状态

| 阶段 | 名称 | 状态 |
| --- | --- | --- |
| V1 | 本地视频会话壳 | 部分完成 — REST API + WebSocket 框架可用 |
| V2 | 抽帧与本地感知 | 部分完成 — OpenCV 检测就绪，fallback 不编造结果 |
| V3 | 视觉模型接口 | 骨架可用 — Provider 可替换，默认关闭，需继续验证 |
| V4 | 语音输入输出 | TTS 骨架可用，ASR 链路已修复（后端转写） |
| V5 | 多模态对话循环 | 主项目优先接口就绪，离线 fallback 可用 |
| V6 | 主项目桥接 | 客户端草稿已存在，接口契约待主项目实现 |
| V7 | 成本和隐私硬化 | 部分配置存在，授权已统一入口，审计可追溯 |
| V8 | 体验打磨 | 未开始 |

**video-companion 当前不是完整产品。**它是独立视频感官模块的开发骨架。它必须依赖主项目提供人格、记忆、关系和长期状态。

## 快速开始

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
python run_tests.py          # 68 tests
python -m app.server         # 启动服务 → http://localhost:8001
```

## 目录

```
video-companion/
  README.md
  HANDOFF.md                  # 交接文档
  config.example.yaml
  requirements.txt
  run_tests.py
  app/
    server.py                 # FastAPI 主服务 + WebSocket
    consent.py                # 授权管理 + 审计
    media_session.py          # 会话状态机 + 主项目优先对话
    camera_source.py          # 摄像头采集抽象
    audio_source.py           # 麦克风 + VAD + 音频缓冲
    local_vision.py           # OpenCV 人脸/动作检测
    vision_provider.py        # 外部视觉模型 Provider
    speech_provider.py        # OpenAI Whisper ASR + TTS
    mnemosyne_client.py       # 主项目 API 客户端
  web/
    index.html / app.js / style.css
  scripts/
    verify_camera.py / verify_vision_provider.py / verify_mnemosyne_bridge.py
  tests/
    8 模块，68 测试
```

## 隐私

- 摄像头、麦克风、外部视觉模型默认关闭
- 需用户分别明确授权
- 不保存原始视频帧和音频
- 授权变更全部审计可追溯
