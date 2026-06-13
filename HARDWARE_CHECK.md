# Hardware Check — 本机硬件验收指南

本文档说明如何在 `ai-vtuber-main` 页面手动验证摄像头、麦克风硬件链路。

---

## 前提

```bash
cd video-companion && python -m app.server    # 终端 1
cd ai-vtuber-main && python main.py            # 终端 2
# 浏览器打开 http://127.0.0.1:9000
```

---

## 1. 验证摄像头

### 步骤

1. 页面左侧"硬件验收"区找到 **摄像头** 面板
2. 点击 **开启** 按钮
3. 浏览器弹出权限请求 → 点击 **允许**
4. 应该看到本地摄像头预览画面
5. 顶部状态栏 **video-companion** 指示灯为绿色
6. "发送帧" 计数器每 2 秒递增（当前帧为 JPEG base64，每 2s 发一次）
7. "检测" 标签显示 presence_status（present / absent / unknown）
8. "最近 observation" 区域显示完整的 observation JSON

### 应该看到的

```text
✅ 摄像头预览画面正常
✅ 发送帧: 1, 2, 3... 递增
✅ 检测: present / absent / unknown (取决于画面)
✅ 最近 observation 有完整 JSON
```

### 如果失败

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 按钮点击后无反应 | 浏览器拒绝摄像头权限 | 检查浏览器地址栏左侧的权限图标 |
| 显示"摄像头不可用: NotAllowedError" | 用户点了"拒绝" | 刷新页面重新授权 |
| 预览黑屏 | 摄像头被其他应用占用 | 关闭其他使用摄像头的应用 |
| 帧发送但 observation 无变化 | OpenCV 未检测到人脸 | 正常 — 非人脸场景下为 absent/unknown |

---

## 2. 验证麦克风

### 步骤

1. 页面左侧"硬件验收"区找到 **麦克风** 面板
2. 点击 **开启** 按钮
3. 浏览器弹出权限请求 → 点击 **允许**
4. **音量条** 应该随说话变化（绿色→红色渐变）
5. "发送段" 计数器每 3 秒递增（模拟语音段发送）
6. 注意：**ASR 为 mock 模式**，不会真实识别你说的话

### 应该看到的

```text
✅ 音量条随声音跳动
✅ 发送段: 1, 2, 3... 递增
⚠  ASR mock — 不代表真实识别
```

### 如果失败

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 按钮点击后无反应 | 浏览器拒绝麦克风权限 | 检查权限设置 |
| 音量条不动 | 麦克风被静音或未选择正确设备 | 检查系统麦克风设置 |
| 发送段不递增 | MediaRecorder 不支持当前浏览器 | 换 Chrome/Edge |

---

## 3. Mock vs 真实 ASR/TTS

### 当前状态（无 API key）

| 组件 | 模式 | 实际能力 |
| --- | --- | --- |
| ASR | mock | 返回固定文本 "[Mock] 模拟语音识别结果。" — 不会识别真实语音 |
| TTS | mock | 返回固定字节 "MOCK" — 不会播放真实语音 |
| Vision | mock (关闭) | 返回 "[Mock] 画面中有一个人..." — 不是真实分析 |

### 配置真实 ASR/TTS

需要 OpenAI API key：

```bash
export OPENAI_API_KEY="sk-..."
```

修改 `video-companion/config.yaml`:

```yaml
speech:
  asr:
    provider: openai_whisper     # 从 mock 改为 openai_whisper
  tts:
    provider: openai_tts         # 从 mock 改为 openai_tts
```

重启 video-companion 后生效。

---

## 4. 无 API key 时不能证明的

| 功能 | 状态 |
| --- | --- |
| 真实语音识别 (ASR) | mock — 不可验证 |
| 真实语音合成 (TTS) | mock — 不可验证 |
| 真实视觉模型分析 | mock — 不可验证 |
| 摄像头帧采集 | ✅ 可验证 |
| 麦克风音频采集 | ✅ 可验证 |
| WebSocket 帧传输 | ✅ 可验证 |
| WebSocket 音频传输 | ✅ 可验证 |
| observation 回收 | ✅ 可验证 |
| 文本对话管道 | ✅ 可验证 (LocalVTuberEngine) |
