"""
头像/虚拟形象状态模块

提供 Live2D / VTuber 表现层预留接口。
当前不驱动真实 Live2D，只输出状态数据供前端展示。
未来可接入 Live2D SDK、VRM、VTS 等。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import enum


class Expression(str, enum.Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    THINKING = "thinking"
    SURPRISED = "surprised"
    SAD = "sad"
    TALKING = "talking"
    IDLE = "idle"


class Attention(str, enum.Enum):
    USER_PRESENT = "user_present"
    USER_ABSENT = "user_absent"
    UNKNOWN = "unknown"


@dataclass
class AvatarState:
    """虚拟形象当前状态（Live2D-ready）"""
    expression: str = "neutral"
    mouth_open: bool = False
    speaking: bool = False
    looking_at_user: bool = True
    attention: str = "unknown"
    emotion: str = "calm"
    # 额外信息
    expression_confidence: float = 0.5
    blink_requested: bool = False
    idle_animation: str = "idle_01"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expression": self.expression,
            "mouth_open": self.mouth_open,
            "speaking": self.speaking,
            "looking_at_user": self.looking_at_user,
            "attention": self.attention,
            "emotion": self.emotion,
            "expression_confidence": self.expression_confidence,
            "blink_requested": self.blink_requested,
            "idle_animation": self.idle_animation,
        }

    @classmethod
    def from_visual_state(cls, presence_status: str,
                          face_mood: Optional[str] = None,
                          motion_level: str = "still") -> "AvatarState":
        """根据视觉状态推导头像状态"""
        state = cls()

        if presence_status == "present":
            state.attention = Attention.USER_PRESENT
            state.looking_at_user = True
            if face_mood and face_mood != "unknown":
                mood_map = {
                    "happy": Expression.HAPPY,
                    "sad": Expression.SAD,
                    "surprised": Expression.SURPRISED,
                    "focused": Expression.NEUTRAL,
                    "confused": Expression.THINKING,
                    "neutral": Expression.NEUTRAL,
                }
                state.expression = mood_map.get(face_mood, Expression.NEUTRAL).value
                state.emotion = face_mood
        elif presence_status == "absent":
            state.attention = Attention.USER_ABSENT
            state.looking_at_user = False
            state.expression = Expression.IDLE
        elif presence_status == "unknown":
            state.attention = Attention.UNKNOWN
            state.looking_at_user = False
            state.expression = Expression.NEUTRAL
        else:
            state.attention = Attention.UNKNOWN
            state.expression = Expression.IDLE

        return state

    @classmethod
    def speaking_state(cls, emotion: str = "calm") -> "AvatarState":
        """生成说话状态"""
        return cls(
            expression="talking",
            mouth_open=True,
            speaking=True,
            looking_at_user=True,
            attention=Attention.USER_PRESENT,
            emotion=emotion,
        )

    @classmethod
    def idle_state(cls) -> "AvatarState":
        """空闲状态"""
        return cls(
            expression=Expression.IDLE,
            mouth_open=False,
            speaking=False,
            looking_at_user=False,
            attention=Attention.UNKNOWN,
            emotion="calm",
        )
