"""
media_session.py 测试套件 — AI VTuber standalone mode

测试覆盖：
1. 会话状态机
2. 对话轮次创建
3. LocalVTuberEngine 本地对话引擎
4. 视觉上下文构建
5. 会话摘要（非空 summary_text）
6. standalone 模式不输出"主项目离线"
7. reply_source 为 local_vtuber
8. 不同视觉状态下的合理回复
"""

import sys, os, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.media_session import (
    MediaSession, SessionState, VideoTurn,
    LocalVTuberEngine, PersonaContext, SessionStats
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
    assert "persona_name" in summary
    assert summary["duration_sec"] >= 0
    # summary_text 不能为空
    assert "summary_text" in summary
    assert len(summary["summary_text"]) > 0


def test_create_turn():
    """测试3: 创建对话轮次"""
    import asyncio
    session = MediaSession()
    asyncio.run(session.start())

    turn = asyncio.run(session.create_turn(
        speech_text="你好",
        speech_confidence=0.9,
        visual_context="检测到用户在镜头前",
    ))
    assert turn.turn_id == 1
    assert turn.user_speech_text == "你好"
    assert turn.visual_context == "检测到用户在镜头前"
    # 默认 reply_source 应为 local_vtuber
    assert turn.reply_source == "local_vtuber"

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


def test_local_vtuber_greeting():
    """测试5: LocalVTuberEngine 问候回复 — 不含主项目离线"""
    import asyncio
    engine = LocalVTuberEngine(PersonaContext(persona_name="Mio", display_name="澪"))

    resp = asyncio.run(engine.generate_response("你好", "", ""))
    assert len(resp) > 0
    # 不能包含"主项目离线"
    assert "主项目离线" not in resp
    assert "主项目人格" not in resp
    assert "离线回退" not in resp
    assert "离线" not in resp.lower()
    # 应该自然回复
    assert "澪" in resp or "Mio" in resp or "你好" in resp or "早上" in resp or "下午" in resp or "晚上" in resp


def test_local_vtuber_visual_present():
    """测试6: present 视觉状态下角色回复 — 不编造"""
    engine = LocalVTuberEngine(PersonaContext(persona_name="Mio", display_name="澪"))

    resp = asyncio.run(engine.generate_response(
        "你好", "检测到用户在镜头前, 情绪happy", ""
    ))
    assert len(resp) > 0
    # 可以说"看到了"但不说"我看到你在做X"
    assert "主项目" not in resp


def test_local_vtuber_visual_unknown():
    """测试7: unknown 视觉状态下不编造看到用户"""
    engine = LocalVTuberEngine(PersonaContext(persona_name="Mio", display_name="澪"))

    # 问"看到什么" + unknown 视觉上下文
    resp = asyncio.run(engine.generate_response(
        "你看到什么了", "无法可靠判断用户是否在场", ""
    ))
    assert len(resp) > 0
    # 不能说"我看到你了"
    assert "我看到你" not in resp
    assert "你在镜头" not in resp


def test_local_vtuber_goodbye():
    """测试8: 再见回复"""
    engine = LocalVTuberEngine(PersonaContext(persona_name="Mio", display_name="澪"))
    resp = asyncio.run(engine.generate_response("拜拜", "", ""))
    assert len(resp) > 0
    assert "主项目" not in resp


def test_local_vtuber_identity():
    """测试9: 身份问题回复"""
    engine = LocalVTuberEngine(PersonaContext(persona_name="Mio", display_name="澪"))
    resp = asyncio.run(engine.generate_response("你是谁", "", ""))
    assert len(resp) > 0
    assert "澪" in resp or "Mio" in resp or "AI VTuber" in resp
    assert "主项目" not in resp


def test_build_visual_context():
    """测试10: 视觉上下文构建"""
    session = MediaSession()

    # present
    obs = {
        "user_present": True,
        "presence_status": "present",
        "face": {"present": True, "rough_mood": "focused"},
        "motion": {"level": "slight"},
        "object_hint": "phone",
    }
    ctx = session._build_visual_context(obs)
    assert "用户在镜头前" in ctx or "检测到用户" in ctx
    assert "focused" in ctx

    # unknown
    obs2 = {"user_present": None, "presence_status": "unknown"}
    ctx2 = session._build_visual_context(obs2)
    assert "无法" in ctx2 or "未知" in ctx2


def test_session_summary():
    """测试11: 会话摘要 — summary_text 非空"""
    session = MediaSession(persona_id="test")
    session.stats = SessionStats(
        start_time=1000.0, end_time=1060.0,
        total_turns=5, total_vision_frames=30,
        interruptions=2, errors=0,
    )
    session._conversation_history.append("User: 你好")
    session._conversation_history.append("AI: 你好！")

    summary = session.get_session_summary()
    assert summary["persona_name"] == "Mio"
    assert summary["total_turns"] == 5
    assert summary["total_vision_frames"] == 30
    assert summary["interruptions"] == 2
    assert summary["reply_mode"] == "standalone_ai_vtuber"
    assert "summary_text" in summary
    assert len(summary["summary_text"]) > 0
    assert "session_id" in summary


def test_conversation_history():
    """测试12: 对话历史管理"""
    import asyncio
    session = MediaSession()
    asyncio.run(session.start())

    session._conversation_history.append("User: 你好")
    session._conversation_history.append("AI: 你好！")
    session._conversation_history.append("User: 今天天气不错")
    session._conversation_history.append("AI: 是啊！")

    history = session.get_conversation_history(limit=2)
    lines = history.split("\n")
    assert len(lines) == 2


def test_pause_resume():
    """测试13: 暂停和恢复"""
    import asyncio
    session = MediaSession()
    asyncio.run(session.start())
    assert session.is_active() == True

    session.pause()
    assert session.get_state() == SessionState.PAUSED
    assert session.is_active() == False

    session.resume()
    assert session.is_active() == True
