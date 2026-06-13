# AI VTuber — Main Project

AI VTuber 主项目。通过 REST + WebSocket 接入 video-companion 实时感知与互动核心。

**video-companion 不是本项目子模块。本项目只调用 video-companion 的 API。**

---

## 快速启动

```bash
cd ai-vtuber-main
pip install fastapi uvicorn httpx
python main.py
```

打开浏览器访问:

```
http://127.0.0.1:9000
```

`main.py` 会自动检测并启动 `video-companion`（如未运行）。

---

## 目录结构

```
ai-vtuber-main/
  main.py              # 主项目入口（启动 VC + Web 服务）
  config.yaml          # 主项目配置
  README.md            # 本文档
  web/
    index.html         # 主 UI 页面
    app.js             # 前端逻辑（WS / session / avatar / audio）
    style.css          # 主项目样式
  scripts/
    smoke_test.py      # 接入验收脚本
```

---

## 主项目负责什么

| 职责 | 本仓库 | video-companion |
| --- | --- | --- |
| 主 UI | ✅ | |
| 角色显示 (占位) | ✅ | |
| 会话控制 (start/stop) | ✅ | |
| 音频播放 | ✅ | |
| avatar_state 展示 | ✅ | |
| transscript 记录 | ✅ | |
| summary 显示 | ✅ | |
| | | |
| 摄像头 / 麦克风 | | ✅ |
| ASR / TTS | | ✅ |
| 视觉观察 | | ✅ |
| 角色对话 (LocalVTuberEngine) | | ✅ |
| 授权管理 | | ✅ |

---

## 配置

`config.yaml`:

```yaml
project:
  name: "AI VTuber"
  version: "0.1.0-dev"

video_companion:
  host: "127.0.0.1"
  port: 8001

persona:
  name: "Mio"
  display_name: "澪"

server:
  host: "127.0.0.1"
  port: 9000
```

---

## Smoke Test

```bash
# 先启动 video-companion
cd ../video-companion && python -m app.server &

# 再运行验收
cd ../ai-vtuber-main
python scripts/smoke_test.py
```

验收标准 15 项 (见 smoke_test.py)。

---

## 当前阶段

v0.1.0-dev — 主项目最小可运行骨架。

**已实现**:
- 自动启动 video-companion
- Web UI (顶栏 / 角色区 / 对话区 / 输入区 / summary)
- WebSocket 连接
- text_input → ai_response.text 显示
- avatar_state 占位角色响应
- audio_base64 播放
- session start/stop
- summary 显示

**未实现 (当前阶段禁止)**:
- 真实 Live2D SDK
- OBS / 直播
- 长期记忆
- 多 Agent
- 复杂 UI
