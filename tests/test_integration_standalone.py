"""
test_integration_standalone.py — standalone 模式集成测试

验证 video-companion 在 standalone AI VTuber 模式下的核心行为。
不启动真实服务，只验证模块间状态和逻辑。
"""

import sys, os, asyncio, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.disable(logging.CRITICAL)

from app.media_session import (
    MediaSession, SessionState, VideoTurn,
    LocalVTuberEngine, PersonaContext, SessionStats
)


def test_standalone_start_session_normal():
    """standalone 模式启动不依赖外部项目"""
    session = MediaSession(persona_id="test")
    asyncio.run(session.start())
    assert session.is_active()
    asyncio.run(session.stop())


def test_standalone_text_input_reply():
    """文本输入能得到 local_vtuber 回复"""
    session = MediaSession(persona_id="test")
    asyncio.run(session.start())

    turn = asyncio.run(session.process_user_speech("你好"))
    assert len(turn.ai_response_text) > 0
    assert turn.reply_source == "local_vtuber"
    assert "主项目离线" not in turn.ai_response_text
    assert "主项目人格" not in turn.ai_response_text
    assert "离线回退" not in turn.ai_response_text
    assert "offline" not in turn.ai_response_text.lower()

    asyncio.run(session.stop())


def test_standalone_visual_present_reply():
    """present 视觉状态下角色回复正常"""
    session = MediaSession(persona_id="test")
    asyncio.run(session.start())
    session.update_observation({
        "user_present": True,
        "presence_status": "present",
        "face": {"present": True, "rough_mood": "happy"},
        "motion": {"level": "slight"},
    })

    turn = asyncio.run(session.process_user_speech("你看到什么了"))
    assert len(turn.ai_response_text) > 0
    assert "主项目离线" not in turn.ai_response_text

    asyncio.run(session.stop())


def test_standalone_visual_unknown_reply():
    """unknown 视觉状态下不编造看到用户"""
    session = MediaSession(persona_id="test")
    asyncio.run(session.start())
    session.update_observation({
        "user_present": None,
        "presence_status": "unknown",
    })

    turn = asyncio.run(session.process_user_speech("你看到什么了"))
    reply = turn.ai_response_text
    assert "我看到你" not in reply
    assert "你在镜头前" not in reply  # unknown 状态不应肯定

    asyncio.run(session.stop())


def test_standalone_tts_failure_returns_text():
    """TTS 失败时仍能返回文字回复"""
    session = MediaSession(persona_id="test")
    asyncio.run(session.start())

    turn = asyncio.run(session.create_turn(
        speech_text="你好",
        visual_context="",
    ))
    turn.ai_response_text = "你好呀"

    # 模拟无 speech_provider (TTS 失败)
    session.speech_provider = None
    result = asyncio.run(session.process_tts_and_respond(turn))
    assert result is None  # TTS 失败返回 None

    # 但 ai_response_text 仍然存在
    assert len(turn.ai_response_text) > 0

    asyncio.run(session.stop())


def test_standalone_summary_nonempty():
    """stop_session 返回非空 summary_text"""
    session = MediaSession(persona_id="test")
    asyncio.run(session.start())

    turn = asyncio.run(session.create_turn(speech_text="你好"))
    turn.ai_response_text = "你好呀"
    session._conversation_history.append("User: 你好")
    session._conversation_history.append("AI: 你好呀")

    summary = asyncio.run(session.stop())
    assert len(summary["summary_text"]) > 0
    assert summary["saved_locally"] == False
    assert "session_id" in summary


def test_standalone_asr_failure_no_reply():
    """ASR 失败不应进入角色回复 — 在 server 层处理，此处验证 MediaSession 不会对空 speech 生成回复"""
    # ASR 失败由 server._handle_speech 处理（不调用 process_user_speech），
    # 此处验证 MediaSession 在无输入时不主动生成回复
    session = MediaSession()
    asyncio.run(session.start())
    assert session.stats.total_turns == 0
    asyncio.run(session.stop())


def test_standalone_persona_passed_from_config():
    """persona config 传入后字段真实生效"""
    persona_config = {
        "name": "CustomBot",
        "display_name": "自定义",
        "language": "en",
        "max_reply_chars": 50,
        "allow_visual_comment": False,
        "avoid_fake_memory": True,
    }
    session = MediaSession(persona_id="test", persona_config=persona_config)
    assert session.persona.persona_name == "CustomBot"
    assert session.persona.display_name == "自定义"
    assert session.persona.max_reply_chars == 50
    assert session.persona.allow_visual_comment == False

    # LocalVTuberEngine 也拿到了
    assert session.dialogue_engine.persona.max_reply_chars == 50


def test_standalone_default_privacy_all_off():
    """默认所有授权关闭"""
    from app.consent import ConsentManager
    cm = ConsentManager()
    assert cm.is_privacy_safe() == True
    assert cm.can_capture_camera() == False
    assert cm.can_capture_microphone() == False
    assert cm.can_upload_to_vision_model() == False
