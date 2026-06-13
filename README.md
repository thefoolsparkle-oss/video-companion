# Video Companion

实时视频陪伴独立项目 —— 从 Project Mnemosyne 拆分出来的视频通话能力模块。

## 功能范围

- 摄像头采集与实时抽帧
- 麦克风输入与语音识别（ASR）
- 本地视觉检测（人脸/人体/动作）
- 外部视觉模型分析（可替换 provider）
- 低延迟语音回复（TTS）
- 与主项目的人格/记忆 API 桥接
- 隐私授权与成本控制

## 不属于本项目

- 长期人格生成与记忆数据库主权
- 核心聊天产品
- 用户账号体系

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 复制配置
cp config.example.yaml config.yaml

# 验证摄像头
python scripts/verify_camera.py

# 启动服务
python app/server.py
```

## 目录结构

```
video-companion/
  README.md
  config.example.yaml
  app/
    __init__.py
    server.py              # 主服务入口
    media_session.py       # 媒体会话管理
    camera_source.py       # 摄像头采集抽象
    audio_source.py        # 音频采集抽象
    local_vision.py        # 本地视觉检测
    vision_provider.py     # 外部视觉模型接口
    speech_provider.py     # ASR/TTS 接口
    mnemosyne_client.py    # 主项目 API 客户端
    consent.py             # 用户授权管理
  web/
    index.html
    app.js
    style.css
  scripts/
    verify_camera.py
    verify_vision_provider.py
    verify_mnemosyne_bridge.py
```

## 阶段计划

| 阶段 | 名称 | 状态 |
| --- | --- | --- |
| V0 | 技术预研 | 待开始 |
| V1 | 本地视频会话壳 | 待开始 |
| V2 | 抽帧与本地感知 | 待开始 |
| V3 | 视觉模型接口 | 待开始 |
| V4 | 语音输入输出 | 待开始 |
| V5 | 多模态对话循环 | 待开始 |
| V6 | 主项目桥接 | 待开始 |
| V7 | 成本和隐私硬化 | 待开始 |
| V8 | 体验打磨 | 待开始 |

## 隐私与安全

- 摄像头、麦克风、外部视觉模型上传默认关闭
- 需用户分别明确授权
- 不保存原始视频帧、音频和截图
- UI 持续显示授权状态
- 用户随时可关闭会话
