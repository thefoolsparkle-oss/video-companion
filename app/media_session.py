"""
媒体会话管理模块 (V5 生产级)

多模态对话循环核心：
- 会话状态机
- VideoTurn 对话轮次
- DialogueEngine — 优先 GPT-4o-mini，无 API key 时模板回退
- 响应生成管线 (视觉上下文 + 语音 → AI 回复)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import time
import asyncio
import os
import logging
import random

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
        parts = [
            f"你是 {self.persona_name}。",
            f"说话风格：{self.speaking_style}。",
            f"与用户的关系：{self.relationship}。",
            "你的回复必须简短、口语化、自然。用中文回复。",
            "回复长度控制在 60 字以内。",
            "如果用户没有在画面中，可以说一句轻松的问候或鼓励。",
        ]
        if self.recent_summary:
            parts.insert(1, f"最近的对话背景：{self.recent_summary}")
        if self.boundaries:
            parts.append(f"对话边界：{'；'.join(self.boundaries)}")
        return "\n".join(parts)


class DialogueEngine:
    """对话引擎 — 优先 GPT-4o-mini"""

    def __init__(self, persona: Optional[PersonaContext] = None,
                 model: str = "gpt-4o-mini"):
        self.persona = persona or PersonaContext()
        self.model = model
        self._llm_client = None
        self._llm_available: Optional[bool] = None

    def set_persona(self, persona: PersonaContext):
        self.persona = persona

    async def generate_response(self, user_text: str,
                                visual_context: str = "",
                                conversation_history: str = "") -> str:
        # 尝试 LLM
        if self._llm_available is None:
            self._llm_available = self._check_llm_available()

        if self._llm_available:
            try:
                start = time.time()
                resp = await self._llm_generate(
                    user_text, visual_context, conversation_history
                )
                elapsed = int((time.time() - start) * 1000)
                if elapsed > 3000:
                    logger.warning("LLM response slow: %dms", elapsed)
                return resp
            except Exception as e:
                logger.warning("LLM failed, using template: %s", e)
                self._llm_available = False

        return self._template_generate(user_text, visual_context)

    def _check_llm_available(self) -> bool:
        try:
            import openai
            api_key = os.environ.get("OPENAI_API_KEY", "")
            return bool(api_key)
        except ImportError:
            return False

    async def _llm_generate(self, user_text: str, visual_context: str,
                            history: str) -> str:
        import openai

        system_prompt = self.persona.to_system_prompt()

        messages = [{"role": "system", "content": system_prompt}]

        if history:
            messages.append({
                "role": "system",
                "content": f"[近期对话历史]\n{history}\n[/历史]"
            })

        visual_part = ""
        if visual_context:
            visual_part = f"\n\n[当前摄像头画面：{visual_context}]"

        messages.append({
            "role": "user",
            "content": user_text + visual_part,
        })

        client = openai.AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=100,
            temperature=0.7,
        )

        return response.choices[0].message.content or "嗯。"

    def _template_generate(self, user_text: str, visual_context: str) -> str:
        """本地模板引擎 — LLM 不可用时的回退"""
        text = user_text.lower().strip()

        if visual_context and "检测到用户" in visual_context:
            parts = visual_context.split(",")
            mood_hint = ""
            for p in parts:
                if "情绪" in p:
                    mood_hint = p.replace("情绪", "").strip()
            if mood_hint:
                return f"看到你了！你今天看起来{mood_hint}呢。"
            return f"我看到了！有什么想聊的吗？"

        if visual_context and "未检测到用户" in visual_context:
            return "我暂时没看到你，但我在这儿呢。在忙什么？"

        greetings = ["你好", "hello", "hi", "嗨", "嘿", "喂"]
        if any(g in text for g in greetings):
            return f"你好！{self.persona.persona_name}在这。今天怎么样？"

        questions = ["?", "？", "什么", "怎么", "为什么", "哪里", "谁", "哪个"]
        if any(q in text for q in questions):
            defaults = [
                "好问题！让我想想……",
                "嗯，这个挺有意思的。",
                "你觉得呢？",
            ]
            return random.choice(defaults)

        thanks = ["谢谢", "感谢", "thank"]
        if any(t in text for t in thanks):
            return "不客气！"

        goodbye = ["再见", "拜拜", "bye", "晚安", "明天见"]
        if any(g in text for g in goodbye):
            return "再见！下次聊。"

        defaults = [
            "嗯，明白了。",
            "有意思，继续说。",
            "好的，我在听呢。",
            "明白了，还有呢？",
            f"{self.persona.persona_name}在认真听。",
        ]
        return random.choice(defaults)


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
        self.dialogue_engine = DialogueEngine(self.persona, model="gpt-4o-mini")

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
        logger.info("Media session active (LLM=%s)",
                     "gpt-4o-mini" if self.dialogue_engine._llm_available else "template")

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

        history_text = "\n".join(self._conversation_history[-6:])
        llm_start = time.time()
        ai_response = await self.dialogue_engine.generate_response(
            speech_text, visual_context, history_text
        )
        llm_ms = int((time.time() - llm_start) * 1000)

        turn = await self.create_turn(
            speech_text=speech_text,
            speech_confidence=speech_confidence,
            visual_observation=self._latest_observation,
            visual_context=visual_context,
        )
        turn.ai_response_text = ai_response
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
        if obs.get("user_present"):
            parts.append("检测到用户在线")
        else:
            parts.append("未检测到用户")
        face = obs.get("face", {})
        if face.get("present"):
            mood = face.get("rough_mood", "unknown")
            if mood != "unknown":
                parts.append(f"情绪{mood}")
        motion = obs.get("motion", {})
        level = motion.get("level", "still")
        if level != "still":
            parts.append(f"动作{level}")
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
            "llm_used": bool(self.dialogue_engine._llm_available),
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
