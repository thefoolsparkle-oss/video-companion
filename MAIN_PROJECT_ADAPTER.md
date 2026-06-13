# Main Project Adapter — 写给 AI VTuber 主项目开发者

本文档说明：AI VTuber 主项目应该如何使用 video-companion。

---

## 核心原则

```text
主项目不应该直接操作摄像头、麦克风、ASR、TTS、视觉观察。
主项目应该把这些交给 video-companion。
```

video-companion 是一个独立 Web 服务。主项目通过 REST + WebSocket 使用它，
就像使用任何其他微服务一样。

---

## 主项目只需要做这几件事

### 启动 video-companion

```python
import subprocess
subprocess.Popen(["python", "-m", "app.server"], cwd="video-companion")
```

或作为独立服务部署。

### 建立 WebSocket

```python
import websockets, json

ws = await websockets.connect("ws://127.0.0.1:8001/ws")
await ws.recv()  # 接收 initial status
```

### 发送帧给它

```python
await ws.send(json.dumps({
    "type": "frame",
    "data": base64_frame,  # JPEG base64
    "width": 640,
    "height": 480,
    "format": "jpeg",
}))
```

### 发送文字/语音给它

```python
await ws.send(json.dumps({"type": "text_input", "text": "你好"}))

# 或语音
await ws.send(json.dumps({
    "type": "speech_input",
    "data": audio_base64,
    "vad_ended": True,
}))
```

### 接收它的回复

```python
msg = json.loads(await ws.recv())
if msg["type"] == "ai_response":
    text = msg["text"]              # → 显示在对话 UI
    audio = msg["audio_base64"]     # → 播放出来
    avatar = msg["avatar_state"]    # → 传给 Live2D 层
```

### 显示 avatar_state

```python
live2d.set_mouth(avatar["mouth_open"] ? "open" : "close")
live2d.set_expression(avatar["expression"])
live2d.set_gaze(avatar["looking_at_user"] ? "user" : "idle")
```

### 拿到 session summary

```python
import httpx
r = await httpx.AsyncClient().post("http://127.0.0.1:8001/api/session/stop")
summary = r.json()["summary"]
# → 保存 summary["summary_text"] 到主项目记录
```

---

## 主项目应该负责什么

| 职责 | 谁做 |
| --- | --- |
| 摄像头/麦克风/ASR/TTS | video-companion |
| 本地视觉观察 | video-companion |
| 本地角色对话 | video-companion (LocalVTuberEngine) |
| avatar_state 计算 | video-companion |
| 会话管理 & 摘要 | video-companion |
| 授权 & 隐私 | video-companion |
| | |
| **主界面 / 角色 UI** | **主项目** |
| **Live2D / VRM / 图像表现** | **主项目** |
| **用户设置页** | **主项目** |
| **保存用户配置** | **主项目** |
| **可选长期记忆** | **主项目** |
| **可选外部 LLM 接入** | **主项目** |
| **可选直播 / OBS** | **主项目** |

---

## 初始化步骤 (完整)

```python
import httpx, websockets, json, asyncio

async def init_video_companion():
    # 1. 等待服务就绪
    client = httpx.AsyncClient(base_url="http://127.0.0.1:8001")
    while True:
        try:
            await client.get("/api/health")
            break
        except:
            await asyncio.sleep(0.5)

    # 2. 启动会话
    r = await client.post("/api/session/start?persona_id=default")

    # 3. 连接 WebSocket
    ws = await websockets.connect("ws://127.0.0.1:8001/ws")
    status = json.loads(await ws.recv())  # initial status

    return client, ws, status
```

## 运行时循环

```python
async def runtime_loop(ws, main_ui):
    async for raw in ws:
        msg = json.loads(raw)
        match msg["type"]:
            case "ai_response":
                main_ui.show_text(msg["text"])
                main_ui.play_audio(msg["audio_base64"])
                main_ui.update_live2d(msg["avatar_state"])
            case "observation":
                main_ui.update_presence(msg["data"]["presence_status"])
            case "system_error":
                main_ui.show_error(msg["code"])
            case "transcript":
                main_ui.add_transcript(msg["speaker"], msg["text"])
```

## 结束会话

```python
r = await client.post("/api/session/stop")
summary = r.json()["summary"]
print(summary["summary_text"])
await ws.close()
```

---

## 不要做的事

- 不要让 video-companion 管理 Live2D SDK
- 不要让 video-companion 提供主 UI
- 不要让 video-companion 存储长期记忆
- 不要让 video-companion 管理用户账号
- 不要在 video-companion 里做 OBS 集成
- 不要默认开启摄像头 (需要用户手动授权)

---

## 可替换的部分

主项目可以替换：

1. **LocalVTuberEngine** — 改为调用外部 LLM 替代规则引擎
2. **ASR/TTS Provider** — 改为更高精度或更低延迟的方案
3. **视觉模型 Provider** — 改为你自己的视觉理解服务

但要保持 API 和 WebSocket 事件协议不变，确保主项目已写好的逻辑继续工作。

---

## 参考

- [Integration Guide](INTEGRATION_GUIDE.md)
- [API Contract](API_CONTRACT.md)
- [Error Codes](ERROR_CODES.md)
- [Legacy Bridge](docs/LEGACY_BRIDGE.md)
