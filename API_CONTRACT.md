# API 接口契约

video-companion ↔ Project Mnemosyne 之间的精确接口定义。

**video-companion 不是人格系统。它只提交观察、候选和会话摘要，不直接写长期记忆。**

---

## 1. GET /api/video/session-context

获取视频会话启动上下文。主项目提供人格公开资料、说话方式、关系状态、近期摘要、对话边界。

### 请求

```
GET /api/video/session-context?persona_id=default
```

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

video-companion 提交用户语音文本和当前视觉画面，主项目根据人格、记忆、关系生成回复。

video-companion **不自己生成人格回复**。主项目不可用时使用离线模板回退（reply_source="offline_template"）。

### 请求 (video-companion → 主项目)

```json
{
    "persona_id": "default",
    "user_text": "今天天气真好",
    "visual_observation": {
        "timestamp": 1718000000.0,
        "user_present": true,
        "presence_status": "present",
        "presence_confidence": 0.8,
        "detector_available": true,
        "face": {"present": true, "count": 1, "rough_mood": "happy"},
        "motion": {"level": "slight", "score": 0.1},
        "object_hint": null,
        "external_analysis": false
    },
    "visual_context": "检测到用户在镜头前, 情绪happy, 画面有slight动作",
    "session_id": "video-companion-12345",
    "turn_index": 3
}
```

### 返回 (主项目 → video-companion)

```json
{
    "reply_text": "是的呢，阳光真好！你今天看起来心情不错。",
    "voice_style": "natural",
    "expression": "smile",
    "memory_policy": {
        "should_extract": false,
        "candidate_only": true
    }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| reply_text | string | 人格回复文本 |
| voice_style | string | 语音风格标记 (natural/gentle/excited/calm) |
| expression | string | 表情标记 (smile/neutral/thinking/surprised) |
| memory_policy.should_extract | bool | 主项目是否将本轮对话提取为长期记忆 |
| memory_policy.candidate_only | bool | 是否仅作为候选（video-companion 无权直接写） |

**如果主项目不可用**：video-companion 使用离线模板回退，reply_source 标记为 "offline_template"。

---

## 3. POST /api/video/observation

video-companion 提交视觉观察候选。**默认 allow_long_term_memory=false**，主项目决定是否采纳。

### 请求 (video-companion → 主项目)

```json
{
    "timestamp": 1718000000.0,
    "description": "用户对着镜头微笑，手中拿着一个蓝色杯子",
    "confidence": 0.85,
    "user_present": true,
    "presence_status": "present",
    "object_hint": "blue cup",
    "allow_long_term_memory": false,
    "evidence_type": "video_observation"
}
```

| 字段 | 说明 |
| --- | --- |
| allow_long_term_memory | **默认 false**。仅当用户显式授权 + 主项目 memory_policy 允许时才为 true |

---

## 4. POST /api/video/session-summary

video-companion 会话结束后提交摘要候选。**不直接写长期记忆**，只提交 memory_candidates。

### 请求 (video-companion → 主项目)

```json
{
    "persona_id": "default",
    "start_time": "2024-06-10T10:00:00",
    "end_time": "2024-06-10T10:05:00",
    "session_duration_sec": 300,
    "total_turns": 12,
    "key_facts": ["用户展示了新手账本"],
    "memory_candidates": ["用户最近在整理计划"],
    "risk_flags": []
}
```

| 字段 | 说明 |
| --- | --- |
| key_facts | 会话中用户主动透露的事实 |
| memory_candidates | 建议纳入长期记忆的内容（**候选**，主项目决定） |
| risk_flags | 需要标记的风险项 |

---

## 5. POST /api/video/consent

同步 video-companion 的用户授权状态到主项目。

### 请求 (video-companion → 主项目)

```json
{
    "camera": true,
    "microphone": true,
    "external_vision_upload": false,
    "save_summary": false,
    "save_observation": false
}
```

---

## video-companion 不负责

- 长期人格生成 → 主项目
- 长期记忆写入 → 主项目（video-companion 只提交候选）
- 核心聊天逻辑 → 主项目
- 用户账号体系 → 主项目
- 人格成长 / 关系变化 → 主项目
- 直接操作主项目数据库 → 禁止
