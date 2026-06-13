"""
音频采集抽象模块 (V4 完善版)

封装麦克风输入、语音播放状态管理。
前端通过 Web Audio API 采集音频；
后端通过本模块管理音频处理管线。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Deque
from collections import deque
import time
import logging

logger = logging.getLogger(__name__)


class AudioState(str, Enum):
    OFF = "off"
    STARTING = "starting"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    chunk_size: int = 1024
    default_on: bool = False
    # VAD 配置
    vad_enabled: bool = True
    vad_silence_threshold_ms: int = 800
    vad_speech_threshold_ms: int = 200
    # 缓冲配置
    max_audio_buffer_sec: int = 30


@dataclass
class AudioChunk:
    """一段音频数据"""
    timestamp: float = 0.0
    data_base64: Optional[str] = None
    data_bytes: Optional[bytes] = None
    duration_ms: int = 0
    sample_rate: int = 16000
    is_speech: bool = False


@dataclass
class AudioMetrics:
    """音频指标"""
    chunks_received: int = 0
    total_duration_ms: int = 0
    speech_segments: int = 0
    errors: int = 0
    start_time: float = 0.0

    @property
    def uptime_sec(self) -> float:
        if self.start_time == 0:
            return 0.0
        return time.time() - self.start_time


class SimpleVAD:
    """简易语音活动检测器

    基于能量阈值判断是否有语音。
    正式版本可替换为 Silero VAD 或 WebRTC VAD。
    """

    def __init__(self, silence_threshold_ms: int = 800,
                 speech_threshold_ms: int = 200,
                 energy_threshold: float = 0.01):
        self.silence_threshold_ms = silence_threshold_ms
        self.speech_threshold_ms = speech_threshold_ms
        self.energy_threshold = energy_threshold

        self._is_speaking: bool = False
        self._speech_start: float = 0.0
        self._silence_start: float = 0.0
        self._current_segment_start: Optional[float] = None

    def process(self, audio_data: bytes, timestamp: float) -> Optional[dict]:
        """处理音频块，返回检测结果"""
        # 计算能量
        energy = self._compute_energy(audio_data)
        is_speech = energy > self.energy_threshold

        result = {
            "is_speech": is_speech,
            "energy": energy,
            "speaking_started": False,
            "speaking_ended": False,
            "segment_duration_ms": 0,
        }

        if is_speech and not self._is_speaking:
            # 检测到说话开始
            if self._current_segment_start is None:
                self._current_segment_start = timestamp
            self._is_speaking = True
            result["speaking_started"] = True

        elif not is_speech and self._is_speaking:
            # 检测到静音
            if self._silence_start == 0:
                self._silence_start = timestamp
            silence_duration = (timestamp - self._silence_start) * 1000
            if silence_duration >= self.silence_threshold_ms:
                # 说话结束
                self._is_speaking = False
                self._silence_start = 0
                result["speaking_ended"] = True
                if self._current_segment_start:
                    result["segment_duration_ms"] = int(
                        (timestamp - self._current_segment_start) * 1000
                    )
                    self._current_segment_start = None
        else:
            self._silence_start = 0

        return result

    def _compute_energy(self, data: bytes) -> float:
        """计算音频能量（简化 RMS）"""
        if not data:
            return 0.0
        try:
            import struct
            sample_count = len(data) // 2
            if sample_count == 0:
                return 0.0
            fmt = f"<{sample_count}h"
            samples = struct.unpack(fmt, data[:sample_count * 2])
            rms = (sum(s * s for s in samples) / sample_count) ** 0.5
            return rms / 32768.0
        except Exception:
            return 0.0

    def reset(self):
        self._is_speaking = False
        self._speech_start = 0.0
        self._silence_start = 0.0
        self._current_segment_start = None


class AudioSource:
    """音频采集源"""

    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        self.state = AudioState.OFF
        self.vad = SimpleVAD(
            silence_threshold_ms=self.config.vad_silence_threshold_ms,
            speech_threshold_ms=self.config.vad_speech_threshold_ms,
        )
        self._audio_buffer: Deque[AudioChunk] = deque()
        self._accumulated_duration_ms: int = 0
        self.metrics = AudioMetrics()

    async def start_listening(self):
        """开始监听"""
        logger.info("Audio source starting...")
        self.state = AudioState.STARTING
        self.metrics = AudioMetrics(start_time=time.time())
        self.vad.reset()
        self._audio_buffer.clear()
        self._accumulated_duration_ms = 0
        self.state = AudioState.LISTENING
        logger.info("Audio source listening")

    async def stop_listening(self):
        """停止监听"""
        logger.info(
            "Audio source stopping (chunks=%d, duration_ms=%d, errors=%d)",
            self.metrics.chunks_received,
            self.metrics.total_duration_ms,
            self.metrics.errors,
        )
        self.state = AudioState.OFF
        self._audio_buffer.clear()
        self._accumulated_duration_ms = 0
        logger.info("Audio source stopped")

    def receive_audio(self, data_base64: str, duration_ms: int = 0,
                      sample_rate: int = 16000) -> Optional[AudioChunk]:
        """接收前端发来的音频数据"""
        if self.state not in (AudioState.LISTENING, AudioState.PROCESSING):
            logger.debug("Audio not listening, dropping chunk")
            return None

        now = time.time()

        chunk = AudioChunk(
            timestamp=now,
            data_base64=data_base64,
            duration_ms=duration_ms,
            sample_rate=sample_rate,
        )

        # VAD 检测
        if self.config.vad_enabled:
            try:
                import base64
                raw = base64.b64decode(data_base64)
                vad_result = self.vad.process(raw, now)
                chunk.is_speech = vad_result["is_speech"]
                if vad_result["speaking_started"]:
                    logger.debug("VAD: speech started")
                if vad_result["speaking_ended"]:
                    logger.debug(
                        "VAD: speech ended (duration=%dms)",
                        vad_result["segment_duration_ms"]
                    )
            except Exception as e:
                logger.debug("VAD processing error: %s", e)

        # 缓冲区管理 —— 限制总时长
        self._accumulated_duration_ms += duration_ms
        max_buffer_ms = self.config.max_audio_buffer_sec * 1000
        while (self._accumulated_duration_ms > max_buffer_ms and
               self._audio_buffer):
            old = self._audio_buffer.popleft()
            self._accumulated_duration_ms -= old.duration_ms

        self._audio_buffer.append(chunk)
        self.metrics.chunks_received += 1
        self.metrics.total_duration_ms += duration_ms
        if chunk.is_speech:
            self.metrics.speech_segments += 1

        return chunk

    async def start_speaking(self):
        self.state = AudioState.SPEAKING

    async def stop_speaking(self):
        if self.state == AudioState.SPEAKING:
            self.state = AudioState.LISTENING

    async def interrupt(self):
        if self.state == AudioState.SPEAKING:
            logger.info("Audio playback interrupted")
            self.state = AudioState.LISTENING

    def get_audio_buffer(self) -> List[AudioChunk]:
        return list(self._audio_buffer)

    def clear_buffer(self):
        self._audio_buffer.clear()
        self._accumulated_duration_ms = 0

    def get_state(self) -> AudioState:
        return self.state

    def is_listening(self) -> bool:
        return self.state == AudioState.LISTENING

    def is_speaking(self) -> bool:
        return self.state == AudioState.SPEAKING

    def set_error(self, message: str):
        self.state = AudioState.ERROR
        self.metrics.errors += 1
        logger.error("Audio error: %s", message)

    def get_metrics(self) -> dict:
        return {
            "state": self.state.value,
            "chunks_received": self.metrics.chunks_received,
            "total_duration_ms": self.metrics.total_duration_ms,
            "speech_segments": self.metrics.speech_segments,
            "uptime_sec": round(self.metrics.uptime_sec, 1),
            "errors": self.metrics.errors,
        }
