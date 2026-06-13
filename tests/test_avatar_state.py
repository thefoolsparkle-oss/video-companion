"""
test_avatar_state.py — avatar_state 字段稳定性测试

验证 avatar_state 在所有场景下字段完整且语义正确。
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.avatar_state import AvatarState, Expression, Attention


def test_avatar_state_to_dict_all_fields():
    """avatar_state.to_dict() 包含所有必需字段"""
    state = AvatarState(
        expression="talking",
        mouth_open=True,
        speaking=True,
        looking_at_user=True,
        attention="user_present",
        emotion="calm",
    )
    d = state.to_dict()

    required_fields = [
        "expression", "mouth_open", "speaking", "looking_at_user",
        "attention", "emotion", "expression_confidence",
        "blink_requested", "idle_animation",
    ]
    for field in required_fields:
        assert field in d, f"Missing field: {field}"

    assert d["expression"] == "talking"
    assert d["mouth_open"] == True
    assert d["speaking"] == True
    assert d["looking_at_user"] == True
    assert d["attention"] == "user_present"
    assert d["emotion"] == "calm"


def test_from_visual_present():
    """present 状态 → looking_at_user=True"""
    state = AvatarState.from_visual_state("present", face_mood="happy")
    d = state.to_dict()
    assert d["attention"] == "user_present"
    assert d["looking_at_user"] == True
    assert d["expression"] == "happy"
    assert d["emotion"] == "happy"


def test_from_visual_absent():
    """absent 状态 → looking_at_user=False"""
    state = AvatarState.from_visual_state("absent")
    d = state.to_dict()
    assert d["attention"] == "user_absent"
    assert d["looking_at_user"] == False
    assert d["expression"] == "idle"


def test_from_visual_unknown():
    """unknown 状态 → 不假装 looking_at_user=True"""
    state = AvatarState.from_visual_state("unknown")
    d = state.to_dict()
    assert d["attention"] == "unknown"
    assert d["looking_at_user"] == False
    assert d["expression"] == "neutral"


def test_speaking_state():
    """speaking_state() → mouth_open=True, speaking=True, expression=talking"""
    state = AvatarState.speaking_state(emotion="calm")
    d = state.to_dict()
    assert d["mouth_open"] == True
    assert d["speaking"] == True
    assert d["expression"] == "talking"
    assert d["emotion"] == "calm"


def test_idle_state():
    """idle_state() → 全部静止"""
    state = AvatarState.idle_state()
    d = state.to_dict()
    assert d["mouth_open"] == False
    assert d["speaking"] == False
    assert d["looking_at_user"] == False
    assert d["expression"] == "idle"


def test_expression_enum_values():
    """Expression 枚举值稳定"""
    expressions = [e.value for e in Expression]
    expected = {"neutral", "happy", "thinking", "surprised", "sad", "talking", "idle"}
    assert set(expressions) == expected


def test_attention_enum_values():
    """Attention 枚举值稳定"""
    attentions = [a.value for a in Attention]
    assert set(attentions) == {"user_present", "user_absent", "unknown"}
