"""
test_api_contract.py — API 输出结构契约测试

验证 REST + WebSocket 输出字段稳定，主项目可依赖。
不启动服务，只验证数据结构和模块级行为。
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.media_session import (
    MediaSession, SessionState, VideoTurn,
    LocalVTuberEngine, PersonaContext, SessionStats
)
from app.avatar_state import AvatarState


def test_video_turn_to_dict_fields():
    """VideoTurn.to_dict() 包含所有契约字段"""
    turn = VideoTurn(
        turn_id=1,
        timestamp=1000.0,
        user_speech_text="你好",
        ai_response_text="你好呀",
        visual_context="无法可靠判断",
        reply_source="local_vtuber",
    )
    d = turn.to_dict()

    required = ["turn_id", "user_text", "ai_response", "visual_context",
                "total_latency_ms", "playback_completed", "playback_interrupted",
                "reply_source"]
    for field in required:
        assert field in d, f"Missing: {field}"

    assert d["reply_source"] == "local_vtuber"
    assert d["user_text"] == "你好"
    assert d["ai_response"] == "你好呀"


def test_ai_response_structure():
    """ai_response 稳定结构：text, audio_base64, avatar_state, reply_source"""
    turn = VideoTurn(
        turn_id=1,
        timestamp=1000.0,
        user_speech_text="你好",
        ai_response_text="你好呀",
        reply_source="local_vtuber",
        ai_response_audio_base64="bW9jaw==",
    )
    avatar_state = AvatarState.speaking_state()
    av = avatar_state.to_dict()

    assert isinstance(turn.ai_response_text, str)
    assert turn.reply_source == "local_vtuber"

    # auto_base64 允许空或非空
    assert isinstance(turn.ai_response_audio_base64, str)

    # avatar_state 字段完整
    assert "expression" in av
    assert "mouth_open" in av
    assert "speaking" in av
    assert "looking_at_user" in av
    assert "attention" in av


def test_session_summary_nonempty():
    """session stop 返回非空 summary_text"""
    session = MediaSession(persona_id="test")
    session.stats = SessionStats(start_time=1000.0, end_time=1060.0, total_turns=3)
    session._conversation_history.append("User: 你好")
    session._conversation_history.append("AI: 你好！")

    summary = session.get_session_summary()
    assert len(summary["summary_text"]) > 0
    assert "session_id" in summary
    assert summary["persona_name"] == "Mio"
    assert summary["saved_locally"] == False
    assert summary["reply_mode"] == "standalone_ai_vtuber"


def test_local_vtuber_reply_never_empty():
    """LocalVTuberEngine 永远不返回空回复"""
    engine = LocalVTuberEngine(PersonaContext(persona_name="Mio", display_name="澪"))

    test_inputs = ["你好", "再见", "你是谁", "谢谢", "今天天气好吗", "什么", ""]
    for text in test_inputs:
        resp = asyncio.run(engine.generate_response(text, "", ""))
        assert len(resp) > 0, f"Empty reply for input: '{text}'"


def test_local_vtuber_no_system_error_in_reply():
    """LocalVTuberEngine 回复不含系统错误词汇"""
    engine = LocalVTuberEngine(PersonaContext(persona_name="Mio", display_name="澪"))

    forbidden = ["系统错误", "服务不可用", "出错了", "error", "Error"]
    test_inputs = ["你好", "再见", "你看到什么了", "你是谁", ""]
    for text in test_inputs:
        resp = asyncio.run(engine.generate_response(text, "", ""))
        for word in forbidden:
            assert word not in resp, f"'{word}' in reply for input '{text}': {resp}"


def test_reply_source_default_local_vtuber():
    """新建 VideoTurn 默认 reply_source 为 local_vtuber"""
    turn = VideoTurn(turn_id=1, timestamp=1000.0)
    assert turn.reply_source == "local_vtuber"


def test_observation_fields():
    """VideoObservation 序列化包含所有稳定字段"""
    from app.local_vision import VideoObservation, FaceDetection, MotionDetection

    obs = VideoObservation(
        timestamp=1000.0,
        user_present=None,
        presence_status="unknown",
        face=FaceDetection(),
        motion=MotionDetection(),
    )
    d = obs.to_dict()

    required = [
        "timestamp", "user_present", "presence_status", "presence_confidence",
        "detector_available", "camera_usable", "face", "body", "motion",
        "object_hint", "brightness", "blur_score", "is_usable",
        "external_analysis", "external_description",
    ]
    for field in required:
        assert field in d, f"Missing observation field: {field}"

    # face 子字段
    face = d["face"]
    assert "present" in face
    assert "count" in face
    assert "rough_mood" in face
