"""
媒体会话管理模块

video-companion 不负责人格回复。
人格回复优先由主项目 turn 接口提供。
离线时使用基础模板回退（明确标注 offline_template）。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import time
import asyncio
import os
import logging

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDING = "ending"
    ENDED = "ended"
    ERROR = "error"


@dataclass
class VideoTurn:
    """一轮多模态对话"""
    turn_id: int
    timestamp: float
    user_speech_text: str = ""
    user_speech_confidence: float = 0.0
    visual_observation: Optional[Dict[str, Any]] = None
    visual_context: str = ""
    ai_response_text: str = ""
    ai_response_audio: Optional[bytes] = None
    ai_response_audio_base64: str = ""
    playback_started: bool = False
    playback_completed: bool = False
    playback_interrupted: bool = False
    asr_duration_ms: int = 0
    vision_duration_ms: int = 0
    llm_duration_ms: int = 0
    tts_duration_ms: int = 0
    # 回复来源: main_project | offline_template | local_fallback
    reply_source: str = "offline_template"

    @property
    def total_latency_ms(self) -> int:
        return self.asr_duration_ms + self.vision_duration_ms + \
               self.llm_duration_ms + self.tts_duration_ms

    def to_dict(self) -> dict:
        return {
            "turn_id": self.turn_id,
            "user_text": self.user_speech_text,
            "ai_response": self.ai_response_text,
            "visual_context": self.visual_context,
            "total_latency_ms": self.total_latency_ms,
            "playback_completed": self.playback_completed,
            "playback_interrupted": self.playback_interrupted,
            "reply_source": self.reply_source,
        }


@dataclass
class SessionStats:
    start_time: float = 0.0
    end_time: float = 0.0
    total_turns: int = 0
    total_speech_duration_ms: int = 0
    total_vision_frames: int = 0
    total_external_analyses: int = 0
    interruptions: int = 0
    errors: int = 0
    total_latency_ms: int = 0
    max_latency_ms: int = 0
    min_latency_ms: int = 999999

    @property
    def duration_sec(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        if self.start_time:
            return time.time() - self.start_time
        return 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.total_turns > 0:
            return self.total_latency_ms / self.total_turns
        return 0.0

    def record_latency(self, ms: int):
        self.total_latency_ms += ms
        self.max_latency_ms = max(self.max_latency_ms, ms)
        self.min_latency_ms = min(self.min_latency_ms, ms)


@dataclass
class PersonaContext:
    persona_id: str = ""
    persona_name: str = "Assistant"
    speaking_style: str = "casual"
    relationship: str = "friend"
    recent_summary: str = ""
    boundaries: List[str] = field(default_factory=list)

    def to_system_prompt(self) -> str:
        """生成 fallback prompt — 仅在主项目不可用时使用。
        video-companion 不是人格系统，此 prompt 是离线回退。
        """
        parts = [
            "你是一个视频陪伴助手的离线回退模式。",
            "主项目人格系统当前不可用。",
            "回复必须简短、口语化、自然。用中文回复。",
            "回复长度控制在 40 字以内。",
            "不要假装知道用户的个人信息、记忆或关系。",
        ]
        if self.recent_summary:
            parts.insert(1, f"参考上下文：{self.recent_summary}")
        return "\n".join(parts)


class DialogueEngine:
    """离线回退对话引擎

    video-companion 不是人格系统。
    此引擎仅在主项目不可用时作为最后回退。
    默认只使用模板，不调用 LLM。
    """

    def __init__(self, persona: Optional[PersonaContext] = None):
        self.persona = persona or PersonaContext()

    def set_persona(self, persona: PersonaContext):
        self.persona = persona

    async def generate_response(self, user_text: str,
                                visual_context: str = "",
                                conversation_history: str = "") -> str:
        return self._template_generate(user_text, visual_context)

    def _template_generate(self, user_text: str, visual_context: str) -> str:
        """离线模板引擎 —— video-companion 不是人格系统，仅做基础回退"""
        text = user_text.lower().strip()

        if visual_context and "检测到用户" in visual_context:
            return "摄像头捕捉到画面了，但主项目人格系统当前未连接。你可以稍后再试。"

        if visual_context and "未检测到用户" in visual_context:
            return "摄像头暂时没有检测到画面变化。"

        greetings = ["你好", "hello", "hi", "嗨", "嘿", "喂"]
        if any(g in text for g in greetings):
            return "你好！语音通道正常。主项目人格系统当前离线。"

        questions = ["?", "？", "什么", "怎么", "为什么", "哪里", "谁", "哪个"]
        if any(q in text for q in questions):
            return "当前是离线回退模式，无法提供完整的对话回复。"

        thanks = ["谢谢", "感谢", "thank"]
        if any(t in text for t in thanks):
            return "不客气。"

        goodbye = ["再见", "拜拜", "bye", "晚安", "明天见"]
        if any(g in text for g in goodbye):
            return "再见。"

        return "语音已收到。主项目人格系统离线，当前是基础回退模式。"


class MediaSession:
    """媒体会话管理器"""

    def __init__(self, persona_id: str = ""):
        self.persona_id = persona_id
        self.state = SessionState.IDLE
        self.stats = SessionStats()
        self._turns: List[VideoTurn] = []
        self._turn_counter: int = 0
        self._state_listeners: list = []
        self._error_count: int = 0

        self.persona = PersonaContext(persona_id=persona_id)
        self.dialogue_engine = DialogueEngine(self.persona)

        self.camera_source = None
        self.audio_source = None
        self.local_vision = None
        self.vision_provider = None
        self.speech_provider = None
        self.consent_manager = None
        self.mnemosyne_client = None

        self._capture_task: Optional[asyncio.Task] = None
        self._latest_observation: Optional[Dict[str, Any]] = None
        self._conversation_history: List[str] = []

    async def start(self):
        logger.info("Starting media session for persona=%s", self.persona_id)
        self.state = SessionState.CONNECTING
        self.stats = SessionStats(start_time=time.time())
        self._turns.clear()
        self._turn_counter = 0
        self._conversation_history.clear()
        self._error_count = 0

        if self.mnemosyne_client:
            try:
                ctx = await self.mnemosyne_client.get_session_context(self.persona_id)
                if ctx:
                    self.persona = PersonaContext(
                        persona_id=ctx.persona_id,
                        persona_name=ctx.persona_name or "Assistant",
                        speaking_style=ctx.speaking_style or "casual",
                        relationship=ctx.relationship_status or "friend",
                        recent_summary=ctx.recent_summary or "",
                        boundaries=ctx.boundaries or [],
                    )
                    self.dialogue_engine.set_persona(self.persona)
            except Exception as e:
                logger.debug("Failed to fetch persona context: %s", e)

        if self.consent_manager and self.consent_manager.can_capture_camera():
            if self.camera_source:
                await self.camera_source.start()
        if self.consent_manager and self.consent_manager.can_capture_microphone():
            if self.audio_source:
                await self.audio_source.start_listening()

        self.state = SessionState.ACTIVE
        self._notify_state_change()
        logger.info("Media session active (mode=%s)",
                      "main_project" if (self.mnemosyne_client and self.mnemosyne_client.is_connected()) else "offline")

    async def stop(self) -> dict:
        logger.info("Stopping media session...")
        self.state = SessionState.ENDING
        self.stats.end_time = time.time()

        if self._capture_task:
            self._capture_task.cancel()
            self._capture_task = None
        if self.camera_source:
            await self.camera_source.stop()
        if self.audio_source:
            await self.audio_source.stop_listening()

        summary = self.get_session_summary()

        if self.mnemosyne_client and self.consent_manager:
            if self.consent_manager.can_save_summary():
                try:
                    await self.mnemosyne_client.post_session_summary(summary)
                except Exception as e:
                    logger.error("Failed to post session summary: %s", e)

        self.state = SessionState.ENDED
        self._notify_state_change()
        logger.info("Media session ended (turns=%d, %.1fs)",
                     self.stats.total_turns, self.stats.duration_sec)
        return summary

    def pause(self):
        if self.state == SessionState.ACTIVE:
            self.state = SessionState.PAUSED

    def resume(self):
        if self.state == SessionState.PAUSED:
            self.state = SessionState.ACTIVE

    async def process_user_speech(self, speech_text: str,
                                  speech_confidence: float = 0.0,
                                  asr_latency_ms: int = 0) -> VideoTurn:
        if self.state != SessionState.ACTIVE:
            raise RuntimeError(f"Session not active: {self.state}")

        t0 = time.time()
        visual_context = ""

        if self._latest_observation:
            visual_context = self._build_visual_context(self._latest_observation)

        # 优先调用主项目 turn 接口
        ai_response = ""
        reply_source = "offline_template"
        llm_ms = 0

        if self.mnemosyne_client and self.mnemosyne_client.is_connected():
            llm_start = time.time()
            try:
                turn_payload = {
                    "persona_id": self.persona_id,
                    "user_text": speech_text,
                    "visual_observation": self._latest_observation,
                    "visual_context": visual_context,
                    "session_id": f"video-companion-{id(self)}",
                    "turn_index": self._turn_counter + 1,
                }
                main_response = await self.mnemosyne_client.post_video_turn(turn_payload)
                llm_ms = int((time.time() - llm_start) * 1000)

                if main_response and main_response.reply_text:
                    ai_response = main_response.reply_text
                    reply_source = "main_project"
                    logger.info("Main project reply (source=%s): %s...",
                                reply_source, ai_response[:40])
            except Exception as e:
                logger.warning("Main project turn failed: %s, falling back to offline", e)

        # 主项目不可用 → 离线模板回退
        if not ai_response:
            llm_start = time.time()
            history_text = "\n".join(self._conversation_history[-6:])
            ai_response = await self.dialogue_engine.generate_response(
                speech_text, visual_context, history_text
            )
            llm_ms = int((time.time() - llm_start) * 1000)
            reply_source = "offline_template"
            logger.info("Offline template reply: %s...", ai_response[:40])

        turn = await self.create_turn(
            speech_text=speech_text,
            speech_confidence=speech_confidence,
            visual_observation=self._latest_observation,
            visual_context=visual_context,
        )
        turn.ai_response_text = ai_response
        turn.reply_source = reply_source
        turn.asr_duration_ms = asr_latency_ms
        turn.llm_duration_ms = llm_ms

        self.stats.record_latency(turn.total_latency_ms)
        self._conversation_history.append(f"User: {speech_text}")
        self._conversation_history.append(f"AI: {ai_response}")

        return turn

    async def process_tts_and_respond(self, turn: VideoTurn) -> Optional[Any]:
        if not self.speech_provider or not turn.ai_response_text:
            return None
        tts_start = time.time()
        try:
            tts_result = await self.speech_provider.synthesize(turn.ai_response_text)
            tts_ms = int((time.time() - tts_start) * 1000)
            turn.tts_duration_ms = tts_ms
            if tts_result and tts_result.audio_data:
                turn.ai_response_audio = tts_result.audio_data
                turn.ai_response_audio_base64 = tts_result.audio_base64
            return tts_result
        except Exception as e:
            self._error_count += 1
            logger.error("TTS failed: %s", e)
            return None

    def update_observation(self, observation: Dict[str, Any]):
        self._latest_observation = observation
        if self.stats.total_vision_frames < 999999:
            self.stats.total_vision_frames += 1

    async def create_turn(self, speech_text: str = "",
                          speech_confidence: float = 0.0,
                          visual_observation: Optional[dict] = None,
                          visual_context: str = "") -> VideoTurn:
        self._turn_counter += 1
        turn = VideoTurn(
            turn_id=self._turn_counter,
            timestamp=time.time(),
            user_speech_text=speech_text,
            user_speech_confidence=speech_confidence,
            visual_observation=visual_observation,
            visual_context=visual_context,
        )
        self._turns.append(turn)
        self.stats.total_turns = self._turn_counter
        return turn

    def interrupt(self):
        if self.speech_provider:
            self.speech_provider.interrupt()
        current = self.get_current_turn()
        if current:
            current.playback_interrupted = True
        self.stats.interruptions += 1

    def _build_visual_context(self, obs: dict) -> str:
        parts = []
        status = obs.get("presence_status", "unknown")

        if status == "present":
            parts.append("检测到用户在镜头前")
            face = obs.get("face", {})
            if face.get("present"):
                mood = face.get("rough_mood", "unknown")
                if mood != "unknown":
                    parts.append(f"情绪{mood}")
        elif status == "absent":
            parts.append("镜头前未检测到用户")
        elif status == "unusable":
            parts.append("摄像头画面暂时不可用（过暗或模糊）")
        else:
            parts.append("无法可靠判断用户是否在场")

        motion = obs.get("motion", {})
        level = motion.get("level", "still")
        if level != "still":
            parts.append(f"画面有{level}动作")
        if obs.get("object_hint"):
            parts.append(f"物品:{obs['object_hint']}")
        return ", ".join(parts)

    def get_current_turn(self) -> Optional[VideoTurn]:
        return self._turns[-1] if self._turns else None

    def get_turns(self, limit: int = 20) -> List[VideoTurn]:
        return self._turns[-limit:]

    def get_conversation_history(self, limit: int = 10) -> str:
        return "\n".join(self._conversation_history[-limit:])

    def get_state(self) -> SessionState:
        return self.state

    def is_active(self) -> bool:
        return self.state == SessionState.ACTIVE

    def get_latest_observation(self) -> Optional[Dict[str, Any]]:
        return self._latest_observation

    def get_session_summary(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "start_time": self.stats.start_time,
            "end_time": self.stats.end_time or time.time(),
            "duration_sec": self.stats.duration_sec,
            "total_turns": self.stats.total_turns,
            "total_vision_frames": self.stats.total_vision_frames,
            "total_external_analyses": self.stats.total_external_analyses,
            "interruptions": self.stats.interruptions,
            "errors": self._error_count,
            "latency": {
                "avg_ms": round(self.stats.avg_latency_ms, 1),
                "max_ms": self.stats.max_latency_ms,
                "min_ms": self.stats.min_latency_ms if self.stats.min_latency_ms < 999999 else 0,
            },
            "reply_mode": "offline_template" if self.mnemosyne_client and not self.mnemosyne_client.is_connected() else "main_project",
            "key_facts": [],
            "memory_candidates": [],
            "risk_flags": [],
        }

    def get_stats_dict(self) -> dict:
        return {"state": self.state.value, "persona_id": self.persona_id,
                **self.get_session_summary()}

    def _notify_state_change(self):
        for listener in self._state_listeners:
            try:
                listener(self.state)
            except Exception:
                pass

    def on_state_change(self, callback):
        self._state_listeners.append(callback)
