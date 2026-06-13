"""
audio_source.py 测试套件

测试覆盖：
1. 初始状态
2. 音频接收
3. VAD 检测
4. 缓冲管理
5. 状态切换
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.audio_source import AudioSource, AudioConfig, AudioState, SimpleVAD, AudioChunk


def test_initial_state():
    """测试1: 初始状态为 OFF"""
    audio = AudioSource()
    assert audio.get_state() == AudioState.OFF
    assert audio.is_listening() == False
    assert audio.is_speaking() == False
    assert len(audio.get_audio_buffer()) == 0


async def _start(audio):
    await audio.start_listening()


def test_start_stop():
    """测试2: 启动监听和停止"""
    import asyncio
    audio = AudioSource()
    asyncio.run(_start(audio))
    assert audio.is_listening() == True
    assert audio.get_state() == AudioState.LISTENING

    asyncio.run(audio.stop_listening())
    assert audio.is_listening() == False
    assert audio.get_state() == AudioState.OFF


def test_receive_audio():
    """测试3: 接收音频数据"""
    import asyncio
    audio = AudioSource()
    asyncio.run(_start(audio))

    # 用假的 base64 数据
    import base64
    fake_audio = base64.b64encode(b"\x00" * 1024).decode()

    chunk = audio.receive_audio(data_base64=fake_audio, duration_ms=200)
    assert chunk is not None
    assert chunk.duration_ms == 200
    assert audio.metrics.chunks_received == 1


def test_audio_drop_when_off():
    """测试4: 关闭状态下丢弃音频"""
    audio = AudioSource()
    chunk = audio.receive_audio(data_base64="test", duration_ms=200)
    assert chunk is None


def test_simple_vad_silence():
    """测试5: VAD 静音检测"""
    vad = SimpleVAD(silence_threshold_ms=500, speech_threshold_ms=200)
    # 静音数据（零值）
    silence = b"\x00" * 1024
    result = vad.process(silence, time.time())
    assert result["is_speech"] == False
    assert result["energy"] < 0.01


def test_simple_vad_speech():
    """测试6: VAD 语音检测"""
    vad = SimpleVAD(silence_threshold_ms=500, speech_threshold_ms=200,
                    energy_threshold=0.001)
    # 模拟有声音数据（非零值）
    speech = bytes([100, 200, 100, 200] * 256)  # 有能量的信号
    result = vad.process(speech, time.time())
    assert result["is_speech"] == True
    assert result["energy"] > 0


def test_simple_vad_transition():
    """测试7: VAD 说话-静音转换"""
    vad = SimpleVAD(silence_threshold_ms=0, speech_threshold_ms=50,
                    energy_threshold=0.001)
    now = time.time()
    speech = bytes([100] * 1024)
    silence = b"\x00" * 1024

    # 开始说话
    r1 = vad.process(speech, now)
    assert r1["speaking_started"] == True

    # 持续说话
    r2 = vad.process(speech, now + 0.1)
    assert r2["speaking_started"] == False

    # 模拟多次静音以累积超过 silence_threshold_ms（0ms 立即触发）
    r3 = vad.process(silence, now + 0.3)
    # silence_threshold_ms=0 means immediate end on first silence
    if not r3["speaking_ended"]:
        r4 = vad.process(silence, now + 0.6)
        assert r4["speaking_ended"] == True
    else:
        assert r3["speaking_ended"] == True


def test_audio_buffer_management():
    """测试8: 音频缓冲管理"""
    import asyncio
    import base64
    audio = AudioSource(
        AudioConfig(max_audio_buffer_sec=1, vad_enabled=False)
    )
    asyncio.run(_start(audio))

    fake_data = base64.b64encode(b"\x00" * 1024).decode()
    for _ in range(10):
        audio.receive_audio(data_base64=fake_data, duration_ms=200)

    buffer = audio.get_audio_buffer()
    assert len(buffer) <= 6  # 1 sec / 200ms = 5 chunks, plus some margin

    audio.clear_buffer()
    assert len(audio.get_audio_buffer()) == 0
