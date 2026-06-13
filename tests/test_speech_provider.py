"""
speech_provider.py 测试套件

测试覆盖：
1. Mock ASR
2. Mock TTS
3. Provider Manager
4. 中断处理
"""

import sys, os, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.speech_provider import (
    SpeechProviderManager, SpeechConfig,
    MockASRProvider, MockTTSProvider,
    TranscriptResult, TTSResult, SpeechSessionState
)


def test_mock_asr():
    """测试1: Mock ASR 转录"""
    asr = MockASRProvider()
    result = asyncio.run(asr.transcribe(b"fake_audio_data"))
    assert result.text != ""
    assert result.confidence > 0
    assert result.is_final == True
    assert result.error is None


def test_mock_tts():
    """测试2: Mock TTS 合成"""
    tts = MockTTSProvider()
    result = asyncio.run(tts.synthesize("Hello world"))
    assert result.audio_data != b""
    assert result.audio_base64 != ""
    assert result.text == "Hello world"
    assert result.error is None


def test_mock_tts_stream():
    """测试3: Mock TTS 流式"""
    tts = MockTTSProvider()

    async def collect():
        chunks = []
        async for chunk in tts.synthesize_stream("Test"):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())
    assert len(chunks) > 0


def test_provider_ready_status():
    """测试4: Provider 就绪状态检查"""
    import os
    mgr = SpeechProviderManager(
        SpeechConfig(asr_provider="openai_whisper", tts_provider="openai_tts")
    )
    asyncio.run(mgr.initialize())
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    assert mgr.is_ready() == has_key


def test_provider_manager_initialization():
    """测试5: Mock Provider Manager 初始化"""
    mgr = SpeechProviderManager(
        SpeechConfig(asr_provider="mock", tts_provider="mock")
    )
    asyncio.run(mgr.initialize())
    assert mgr.asr.name == "mock"
    assert mgr.tts.name == "mock"
    assert mgr.state == SpeechSessionState.IDLE
    assert mgr.is_ready() == True


def test_provider_manager_transcribe():
    """测试6: Provider Manager 转录"""
    mgr = SpeechProviderManager(
        SpeechConfig(asr_provider="mock")
    )
    asyncio.run(mgr.initialize())

    result = asyncio.run(mgr.transcribe(b"test_audio"))
    assert result.text != ""
    assert mgr.get_stats()["transcript_count"] == 1


def test_provider_manager_synthesize():
    """测试7: Provider Manager 合成"""
    mgr = SpeechProviderManager(
        SpeechConfig(tts_provider="mock")
    )
    asyncio.run(mgr.initialize())

    result = asyncio.run(mgr.synthesize("你好世界"))
    assert result.audio_data != b""
    assert result.text == "你好世界"
    assert mgr.get_stats()["tts_count"] == 1


def test_interrupt():
    """测试8: 中断播放"""
    mgr = SpeechProviderManager(
        SpeechConfig(tts_provider="mock")
    )
    asyncio.run(mgr.initialize())

    asyncio.run(mgr.synthesize("long text"))
    mgr.interrupt()
    assert mgr.state == SpeechSessionState.INTERRUPTED


def test_empty_text_synthesize():
    """测试9: 空文本合成"""
    mgr = SpeechProviderManager(
        SpeechConfig(tts_provider="mock")
    )
    asyncio.run(mgr.initialize())

    result = asyncio.run(mgr.synthesize(""))
    assert result.text == ""
    assert result.audio_data == b""


def test_health_checks():
    """测试10: 健康检查"""
    mock_asr = MockASRProvider()
    assert asyncio.run(mock_asr.health_check()) == True

    mock_tts = MockTTSProvider()
    assert asyncio.run(mock_tts.health_check()) == True
