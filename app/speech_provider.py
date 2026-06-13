"""
语音识别 (ASR) 和语音合成 (TTS) Provider 接口 — 工业级实现

Provider:
  ASR: OpenAI Whisper (云端) ｜ 默认，生产首选
  TTS: OpenAI TTS (tts-1 / tts-1-hd) ｜ ElevenLabs (备选 premium)

Mock 仅保留用于单元测试，不暴露给生产配置。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, AsyncIterator, Dict, Any, List
import time
import os
import base64
import tempfile
import logging
import asyncio

logger = logging.getLogger(__name__)


class SpeechSessionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


@dataclass
class TranscriptResult:
    """语音识别结果"""
    text: str = ""
    language: str = "zh"
    confidence: float = 0.0
    is_final: bool = True
    duration_ms: int = 0
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class TTSResult:
    """语音合成结果"""
    audio_data: bytes = b""
    audio_base64: str = ""
    format: str = "mp3"
    duration_ms: int = 0
    text: str = ""
    latency_ms: int = 0
    error: Optional[str] = None


@dataclass
class SpeechConfig:
    asr_provider: str = "openai_whisper"
    asr_model: str = "whisper-1"
    asr_language: str = "zh"
    tts_provider: str = "openai_tts"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_speed: float = 1.0
    tts_streaming: bool = True
    tts_interruptible: bool = True
    api_key_env: str = "OPENAI_API_KEY"
    elevenlabs_api_key_env: str = "ELEVENLABS_API_KEY"


# ============ ASR Providers ============

class BaseASRProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_data: bytes,
                         language: Optional[str] = None) -> TranscriptResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class OpenAWhisperASR(BaseASRProvider):
    """OpenAI Whisper — 云端最高精度 ASR"""

    def __init__(self, config: SpeechConfig):
        self.config = config
        self._client = None

    @property
    def name(self) -> str:
        return f"openai/{self.config.asr_model}"

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                api_key = os.environ.get(self.config.api_key_env, "")
                if not api_key:
                    raise RuntimeError(
                        f"ASR: {self.config.api_key_env} not set"
                    )
                self._client = AsyncOpenAI(api_key=api_key)
            except ImportError:
                raise RuntimeError("ASR: pip install openai")
        return self._client

    async def transcribe(self, audio_data: bytes,
                         language: Optional[str] = None) -> TranscriptResult:
        try:
            client = self._ensure_client()
            start = time.time()

            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_data)
                tmp_path = f.name

            try:
                with open(tmp_path, "rb") as f:
                    response = await client.audio.transcriptions.create(
                        model=self.config.asr_model,
                        file=f,
                        language=language or self.config.asr_language,
                        response_format="verbose_json",
                    )
            finally:
                os.unlink(tmp_path)

            elapsed = int((time.time() - start) * 1000)
            return TranscriptResult(
                text=response.text,
                language=language or self.config.asr_language,
                confidence=getattr(response, 'confidence', 0.95),
                is_final=True,
                duration_ms=getattr(response, 'duration', 0) * 1000 if hasattr(response, 'duration') else 0,
                latency_ms=elapsed,
            )
        except Exception as e:
            logger.error("Whisper ASR failed: %s", e)
            return TranscriptResult(error=str(e)[:200])

    async def health_check(self) -> bool:
        try:
            self._ensure_client()
            return True
        except Exception:
            return False


# ============ TTS Providers ============

class BaseTTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> TTSResult:
        ...

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class OpenAITTSProvider(BaseTTSProvider):
    """OpenAI TTS — 高质量语音合成 (tts-1 / tts-1-hd)"""

    VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "ash", "coral", "sage"]

    def __init__(self, config: SpeechConfig):
        self.config = config
        self._client = None

    @property
    def name(self) -> str:
        return f"openai/{self.config.tts_model}/{self.config.tts_voice}"

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                api_key = os.environ.get(self.config.api_key_env, "")
                if not api_key:
                    raise RuntimeError(
                        f"TTS: {self.config.api_key_env} not set"
                    )
                self._client = AsyncOpenAI(api_key=api_key)
            except ImportError:
                raise RuntimeError("TTS: pip install openai")
        return self._client

    async def synthesize(self, text: str) -> TTSResult:
        try:
            client = self._ensure_client()
            start = time.time()
            response = await client.audio.speech.create(
                model=self.config.tts_model,
                voice=self.config.tts_voice,
                input=text,
                speed=self.config.tts_speed,
                response_format="mp3",
            )
            audio_data = response.content
            elapsed = int((time.time() - start) * 1000)
            return TTSResult(
                audio_data=audio_data,
                audio_base64=base64.b64encode(audio_data).decode(),
                format="mp3",
                duration_ms=len(text) * 80,  # 粗略估计
                latency_ms=elapsed,
                text=text,
            )
        except Exception as e:
            logger.error("OpenAI TTS failed: %s", e)
            return TTSResult(error=str(e)[:200], text=text)

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        result = await self.synthesize(text)
        if result.audio_data:
            yield result.audio_data

    async def health_check(self) -> bool:
        try:
            self._ensure_client()
            return True
        except Exception:
            return False


class ElevenLabsTTSProvider(BaseTTSProvider):
    """ElevenLabs — 业界最高质量语音合成"""

    VOICES = {
        "alloy": "21m00Tcm4TlvDq8ikWAM",   # Rachel
        "echo": "EXAVITQu4vr4xnSDxMaL",    # Bella
        "nova": "pNInz6obpgDQGcFmaJgB",   # Adam
    }

    def __init__(self, config: SpeechConfig):
        self.config = config
        self._client = None
        self._voice_id = self.VOICES.get(
            self.config.tts_voice,
            "21m00Tcm4TlvDq8ikWAM"
        )

    @property
    def name(self) -> str:
        return f"elevenlabs/{self.config.tts_voice}"

    def _ensure_client(self):
        if self._client is None:
            try:
                from elevenlabs import AsyncElevenLabs
                api_key = os.environ.get(self.config.elevenlabs_api_key_env, "")
                if not api_key:
                    raise RuntimeError("TTS: ELEVENLABS_API_KEY not set")
                self._client = AsyncElevenLabs(api_key=api_key)
            except ImportError:
                raise RuntimeError("TTS: pip install elevenlabs")
        return self._client

    async def synthesize(self, text: str) -> TTSResult:
        try:
            client = self._ensure_client()
            start = time.time()
            audio_iter = client.text_to_speech.convert(
                voice_id=self._voice_id,
                output_format="mp3_44100_128",
                text=text,
                model_id="eleven_multilingual_v2",
            )
            chunks = []
            async for chunk in audio_iter:
                chunks.append(chunk)
            audio_data = b"".join(chunks)
            elapsed = int((time.time() - start) * 1000)
            return TTSResult(
                audio_data=audio_data,
                audio_base64=base64.b64encode(audio_data).decode(),
                format="mp3",
                duration_ms=len(text) * 80,
                latency_ms=elapsed,
                text=text,
            )
        except Exception as e:
            logger.error("ElevenLabs TTS failed: %s", e)
            return TTSResult(error=str(e)[:200], text=text)

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        try:
            client = self._ensure_client()
            audio_iter = client.text_to_speech.convert(
                voice_id=self._voice_id,
                output_format="mp3_44100_128",
                text=text,
                model_id="eleven_multilingual_v2",
            )
            async for chunk in audio_iter:
                yield chunk
        except Exception:
            yield b""

    async def health_check(self) -> bool:
        try:
            self._ensure_client()
            return True
        except Exception:
            return False


# ============ Provider 注册表 ============

# ============ Mock Providers (仅测试用) ============

class MockASRProvider(BaseASRProvider):
    def __init__(self, config=None):
        pass
    @property
    def name(self) -> str:
        return "mock"
    async def transcribe(self, audio_data: bytes, language: Optional[str] = None) -> TranscriptResult:
        return TranscriptResult(text="[Mock] 模拟语音识别结果。", confidence=0.9, is_final=True)
    async def health_check(self) -> bool:
        return True


class MockTTSProvider(BaseTTSProvider):
    def __init__(self, config=None):
        pass
    @property
    def name(self) -> str:
        return "mock"
    async def synthesize(self, text: str) -> TTSResult:
        return TTSResult(audio_data=b"MOCK", audio_base64=base64.b64encode(b"MOCK").decode(),
                         format="mp3", text=text, latency_ms=50)
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        yield b"MOCK"
    async def health_check(self) -> bool:
        return True


# ============ Provider 注册表 ============

ASR_REGISTRY = {
    "openai_whisper": OpenAWhisperASR,
    "mock": MockASRProvider,
}

TTS_REGISTRY = {
    "openai_tts": OpenAITTSProvider,
    "elevenlabs": ElevenLabsTTSProvider,
    "mock": MockTTSProvider,
}


class SpeechProviderManager:
    """语音服务管理器 — 生产级"""

    def __init__(self, config: Optional[SpeechConfig] = None):
        self.config = config or SpeechConfig()
        self.asr: Optional[BaseASRProvider] = None
        self.tts: Optional[BaseTTSProvider] = None
        self.state = SpeechSessionState.IDLE
        self._transcript_count: int = 0
        self._tts_count: int = 0
        self._error_count: int = 0
        self._interrupted: bool = False
        self._asr_healthy: bool = False
        self._tts_healthy: bool = False

    async def initialize(self):
        logger.info("Initializing speech providers...")

        # ASR
        asr_cls = ASR_REGISTRY.get(self.config.asr_provider)
        if asr_cls:
            try:
                self.asr = asr_cls(self.config)
                self._asr_healthy = await self.asr.health_check()
                if self._asr_healthy:
                    logger.info("ASR: %s READY", self.asr.name)
                else:
                    logger.warning("ASR: %s — API key missing", self.config.asr_provider)
            except Exception as e:
                logger.error("ASR init failed: %s", e)
        else:
            logger.error("Unknown ASR provider: %s", self.config.asr_provider)

        # TTS
        tts_cls = TTS_REGISTRY.get(self.config.tts_provider)
        if tts_cls:
            try:
                self.tts = tts_cls(self.config)
                self._tts_healthy = await self.tts.health_check()
                if self._tts_healthy:
                    logger.info("TTS: %s READY", self.tts.name)
                else:
                    logger.warning("TTS: %s — API key missing", self.config.tts_provider)
            except Exception as e:
                logger.error("TTS init failed: %s", e)
        else:
            logger.error("Unknown TTS provider: %s", self.config.tts_provider)

    async def transcribe(self, audio_data: bytes) -> TranscriptResult:
        self._transcript_count += 1
        if not self.asr or not self._asr_healthy:
            msg = "ASR unavailable: set OPENAI_API_KEY"
            logger.warning(msg)
            return TranscriptResult(error=msg)

        self.state = SpeechSessionState.PROCESSING
        try:
            result = await self.asr.transcribe(
                audio_data, self.config.asr_language
            )
            if result.error:
                self._error_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            return TranscriptResult(error=str(e)[:200])
        finally:
            self.state = SpeechSessionState.IDLE

    async def synthesize(self, text: str) -> TTSResult:
        if not text.strip():
            return TTSResult(text=text)
        if not self.tts or not self._tts_healthy:
            msg = "TTS unavailable: set API key"
            logger.warning(msg)
            return TTSResult(error=msg, text=text)

        self._tts_count += 1
        self._interrupted = False
        self.state = SpeechSessionState.SPEAKING
        try:
            result = await self.tts.synthesize(text)
            if result.error:
                self._error_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            return TTSResult(error=str(e)[:200], text=text)
        finally:
            if not self._interrupted:
                self.state = SpeechSessionState.IDLE

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        if not self.tts or not self._tts_healthy:
            yield b""
            return
        self._interrupted = False
        self.state = SpeechSessionState.SPEAKING
        try:
            async for chunk in self.tts.synthesize_stream(text):
                if self._interrupted:
                    break
                yield chunk
        finally:
            if not self._interrupted:
                self.state = SpeechSessionState.IDLE

    def interrupt(self):
        self._interrupted = True
        self.state = SpeechSessionState.INTERRUPTED

    def get_state(self) -> SpeechSessionState:
        return self.state

    def is_ready(self) -> bool:
        return bool(self.asr and self._asr_healthy and
                    self.tts and self._tts_healthy)

    def get_stats(self) -> dict:
        return {
            "asr_provider": self.asr.name if self.asr else "none",
            "asr_healthy": self._asr_healthy,
            "tts_provider": self.tts.name if self.tts else "none",
            "tts_healthy": self._tts_healthy,
            "state": self.state.value,
            "transcript_count": self._transcript_count,
            "tts_count": self._tts_count,
            "errors": self._error_count,
        }
