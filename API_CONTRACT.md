# Legacy Bridge 接口契约

**默认关闭。** 仅在 `legacy_bridge.enabled: true` 时激活。

video-companion ↔ Project Mnemosyne 之间的历史接口定义。
当前项目以 standalone AI VTuber 模式运行，这些接口仅作为可选的历史兼容桥接。

video-companion 不直接写长期记忆。只提交候选摘要，由接收方决定是否采纳。

---

## 1. GET /api/video/session-context

获取视频会话启动上下文。

### 返回 (主项目 → video-companion)

```json
{
    "persona_id": "default",
    "persona_name": "澪",
    "persona_public_info": {},
    "speaking_style": "casual",
    "relationship_status": "friend",
    "recent_summary": "最近聊了天气和手账本",
    "boundaries": ["不讨论政治"],
    "consent_state": {
        "camera": false,
        "microphone": false,
        "external_vision": false
    }
}
```

---

## 2. POST /api/video/turn

video-companion 提交用户语音文本和当前视觉画面。

### 请求 (video-companion → 主项目)

```json
{
    "persona_id": "default",
    "user_text": "今天天气真好",
    "visual_observation": {
        "timestamp": 1718000000.0,
        "user_present": true,
        "presence_status": "present"
    },
    "visual_context": "检测到用户在镜头前",
    "session_id": "video-companion-12345",
    "turn_index": 3
}
```

### 返回 (主项目 → video-companion)

```json
{
    "reply_text": "是的呢，阳光真好！",
    "voice_style": "natural",
    "expression": "smile",
    "memory_policy": {
        "should_extract": false,
        "candidate_only": true
    }
}
```

---

## 3. POST /api/video/observation

video-companion 提交视觉观察候选。

---

## 4. POST /api/video/session-summary

video-companion 会话结束后提交摘要候选。

---

## 5. POST /api/video/consent

同步 video-companion 的用户授权状态。
