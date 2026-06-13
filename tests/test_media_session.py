"""
media_session.py 测试套件

测试覆盖：
1. 会话状态机
2. 对话轮次创建
3. 对话引擎
4. 视觉上下文构建
5. 会话摘要
"""

import sys, os, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.media_session import (
    MediaSession, SessionState, VideoTurn,
    DialogueEngine, PersonaContext, SessionStats
)


def test_initial_state():
    """测试1: 初始会话状态"""
    session = MediaSession()
    assert session.get_state() == SessionState.IDLE
    assert session.is_active() == False
    assert session.get_current_turn() is None
    assert session.stats.total_turns == 0


def test_session_start_stop():
    """测试2: 会话启动和停止"""
    import asyncio
    session = MediaSession(persona_id="test_persona")

    asyncio.run(session.start())
    assert session.is_active() == True
    assert session.get_state() == SessionState.ACTIVE
    assert session.stats.start_time > 0

    summary = asyncio.run(session.stop())
    assert session.is_active() == False
    assert session.get_state() == SessionState.ENDED
    assert summary["persona_id"] == "test_persona"
    assert summary["duration_sec"] >= 0


def test_create_turn():
    """测试3: 创建对话轮次"""
    import asyncio
    session = MediaSession()
    asyncio.run(session.start())

    turn = asyncio.run(session.create_turn(
        speech_text="你好",
        speech_confidence=0.9,
        visual_context="检测到用户在线",
    ))
    assert turn.turn_id == 1
    assert turn.user_speech_text == "你好"
    assert turn.visual_context == "检测到用户在线"

    turn2 = asyncio.run(session.create_turn(speech_text="再见"))
    assert turn2.turn_id == 2

    turns = session.get_turns()
    assert len(turns) == 2


def test_video_turn_latency():
    """测试4: VideoTurn 延迟计算"""
    turn = VideoTurn(
        turn_id=1, timestamp=time.time(),
        asr_duration_ms=200,
        vision_duration_ms=150,
        llm_duration_ms=500,
        tts_duration_ms=300,
    )
    assert turn.total_latency_ms == 1150

    turn.tts_duration_ms = 100
    assert turn.total_latency_ms == 950


def test_dialogue_engine_template():
    """测试5: 对话引擎模板回复"""
    import asyncio
    engine = DialogueEngine(PersonaContext(persona_name="小明"))

    # 问候
    resp = asyncio.run(engine.generate_response("你好", "", ""))
    assert len(resp) > 0

    # 带视觉上下文
    resp = asyncio.run(engine.generate_response(
        "在吗",
        "检测到用户在线, 情绪happy",
        ""
    ))
    assert len(resp) > 0

    # 再见
    resp = asyncio.run(engine.generate_response("拜拜", "", ""))
    assert len(resp) > 0
    assert "再见" in resp or "聊" in resp


def test_build_visual_context():
    """测试6: 视觉上下文构建"""
    session = MediaSession()

    obs = {
        "user_present": True,
        "face": {"present": True, "rough_mood": "focused"},
        "motion": {"level": "slight"},
        "object_hint": "phone",
    }
    ctx = session._build_visual_context(obs)
    assert "检测到用户在线" in ctx
    assert "focused" in ctx
    assert "slight" in ctx
    assert "phone" in ctx

    obs2 = {"user_present": False}
    ctx2 = session._build_visual_context(obs2)
    assert "未检测到用户" in ctx2


def test_session_summary():
    """测试7: 会话摘要"""
    session = MediaSession(persona_id="test")
    session.stats = SessionStats(
        start_time=1000.0, end_time=1060.0,
        total_turns=5, total_vision_frames=30,
        interruptions=2, errors=0,
    )

    summary = session.get_session_summary()
    assert summary["persona_id"] == "test"
    assert summary["total_turns"] == 5
    assert summary["total_vision_frames"] == 30
    assert summary["interruptions"] == 2
    assert summary["latency"]["avg_ms"] == 0  # 没有 turn 记录


def test_conversation_history():
    """测试8: 对话历史管理"""
    import asyncio
    session = MediaSession()
    asyncio.run(session.start())

    # 模拟对话
    session._conversation_history.append("User: 你好")
    session._conversation_history.append("AI: 你好！")
    session._conversation_history.append("User: 今天天气不错")
    session._conversation_history.append("AI: 是啊！")

    history = session.get_conversation_history(limit=2)
    lines = history.split("\n")
    assert len(lines) == 2


def test_pause_resume():
    """测试9: 暂停和恢复"""
    import asyncio
    session = MediaSession()
    asyncio.run(session.start())
    assert session.is_active() == True

    session.pause()
    assert session.get_state() == SessionState.PAUSED
    assert session.is_active() == False

    session.resume()
    assert session.is_active() == True
