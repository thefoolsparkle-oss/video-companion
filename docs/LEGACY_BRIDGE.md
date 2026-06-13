# Legacy Bridge (历史兼容)

**默认关闭。** 仅在 `legacy_bridge.enabled: true` 时激活。

video-companion 当前作为独立 AI VTuber 核心运行，不依赖任何外部项目。
此桥接仅用于与旧版 Project Mnemosyne / 忆界树 的历史兼容对接。

---

## 启用

```yaml
legacy_bridge:
  enabled: true
  api_base: "http://127.0.0.1:8000"
```

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/video/session-context?persona_id=...` | 获取会话上下文 |
| POST | `/api/video/turn` | 提交 turn 并获取回复 |
| POST | `/api/video/session-summary` | 回写会话摘要 |
| POST | `/api/video/observation` | 回写视觉观察 |
| POST | `/api/video/consent` | 同步授权状态 |

## 行为

- bridge 不可达时，video-companion 正常使用 `LocalVTuberEngine`
- bridge 连接成功时，其回复会覆盖 local_vtuber 回复（`reply_source: legacy_bridge`）
- bridge 不会覆盖 config.persona 中已设置的 display_name、max_reply_chars 等本地配置

## 注意

此桥接不是 video-companion 的主路径，不保证长期维护。
