"""
媒体会话管理模块 — AI VTuber 本地对话引擎

独立运行模式，不依赖主项目。
LocalVTuberEngine 提供轻量本地角色对话能力。
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
    # 回复来源: local_vtuber | external_llm_optional | legacy_bridge | mock
    reply_source: str = "local_vtuber"

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
    persona_name: str = "Mio"
    display_name: str = "澪"
    language: str = "zh"
    speaking_style: str = "自然、简短、温和、稍微冷静"
    relationship: str = "friend"
    recent_summary: str = ""
    boundaries: List[str] = field(default_factory=list)
    max_reply_chars: int = 100
    allow_visual_comment: bool = True
    avoid_fake_memory: bool = True

    def to_system_prompt(self) -> str:
        parts = [
            f"你是{self.display_name}({self.persona_name})，一个AI VTuber。",
            f"说话风格：{self.speaking_style}。",
            "回复必须简短、口语化、自然。用中文回复。",
            f"回复尽量控制在{self.max_reply_chars}字以内。",
            "你不会假装知道用户的个人信息或长期记忆。",
            "你只根据当前会话的视觉画面和最近几轮对话来回应。",
            "当不确定视觉画面时，诚实说明不确定。",
        ]
        if self.boundaries:
            parts.append(f"边界：{'、'.join(self.boundaries)}。")
        return "\n".join(parts)


class LocalVTuberEngine:
    """AI VTuber 本地对话引擎

    使用模板 + 规则生成自然回复。
    不依赖外部 LLM，不假装有长期记忆。
    结合视觉上下文和短期对话历史生成回复。
    """

    def __init__(self, persona: Optional[PersonaContext] = None):
        self.persona = persona or PersonaContext()
        self._turn_count: int = 0

    def set_persona(self, persona: PersonaContext):
        self.persona = persona

    async def generate_response(self, user_text: str,
                                visual_context: str = "",
                                conversation_history: str = "") -> str:
        self._turn_count += 1
        return self._template_generate(user_text, visual_context, conversation_history)

    def _template_generate(self, user_text: str, visual_context: str,
                           conversation_history: str) -> str:
        name = self.persona.display_name or self.persona.persona_name or "Mio"
        text = user_text.strip()
        text_lower = text.lower()
        max_chars = self.persona.max_reply_chars

        # 确定视觉状态
        vis_present = "检测到用户" in visual_context or "用户在镜头前" in visual_context
        vis_absent = "未检测到用户" in visual_context or "未检测到" in visual_context
        vis_unusable = "不可用" in visual_context or "过暗" in visual_context or "模糊" in visual_context
        vis_unknown = not vis_present and not vis_absent and not vis_unusable

        # 计算当前时段
        hour = self._get_hour()

        # 1. 用户问视觉相关
        if self._is_visual_question(text_lower):
            if vis_present:
                return self._truncate("嗯，画面里有人哦，你是在镜头前对吧？", max_chars)
            elif vis_absent:
                return self._truncate("我暂时没看到画面里有人。", max_chars)
            elif vis_unusable:
                return self._truncate("画面现在不太清楚，可能是光线比较暗。", max_chars)
            else:
                return self._truncate("我不太确定画面里现在有没有人，摄像头好像还没准备好。", max_chars)

        # 2. 用户问系统状态
        if self._is_status_question(text_lower):
            return self._build_status_reply(visual_context, max_chars)

        # 3. 用户问"你是谁"
        if self._is_identity_question(text_lower):
            return self._truncate(f"我是{name}，你的AI VTuber伙伴。我可以看到画面、听到你说话，然后自然地回应你。想聊点什么？", max_chars)

        # 4. 问候
        greetings = ["你好", "hello", "hi", "嗨", "嘿", "喂", "在吗", "在不在"]
        if any(g in text_lower for g in greetings):
            if hour < 6:
                time_greeting = "这么晚了还没睡呀"
            elif hour < 12:
                time_greeting = "早上好"
            elif hour < 18:
                time_greeting = "下午好"
            else:
                time_greeting = "晚上好"

            if vis_present and self.persona.allow_visual_comment:
                return self._truncate(f"{time_greeting}～看到你啦。有什么想聊的吗？", max_chars)
            return self._truncate(f"{time_greeting}！我是{name}，有什么想聊的吗？", max_chars)

        # 5. 再见
        goodbye = ["再见", "拜拜", "bye", "晚安", "明天见", "下次见"]
        if any(g in text_lower for g in goodbye):
            if hour < 6:
                return self._truncate("晚安，早点休息哦～", max_chars)
            return self._truncate("嗯，下次见啦。", max_chars)

        # 6. 感谢
        thanks = ["谢谢", "感谢", "thank"]
        if any(t in text_lower for t in thanks):
            return self._truncate("不客气～有什么需要的随时说。", max_chars)

        # 7. 天气/日常闲聊
        weather_words = ["天气", "下雨", "晴天", "好热", "好冷", "凉快"]
        if any(w in text_lower for w in weather_words):
            return self._truncate("天气变化确实影响心情呢。你那边现在怎么样？", max_chars)

        # 8. 情绪表达
        if self._is_emotional(text_lower):
            return self._truncate("听起来你有些感受想说出来，我在听。", max_chars)

        # 9. 问题
        questions = ["?", "？", "什么", "怎么", "为什么", "哪里", "谁"]
        if any(q in text_lower for q in questions):
            if vis_present and self.persona.allow_visual_comment:
                return self._truncate("嗯…是个好问题。我看到你在镜头前，感觉你挺认真的。", max_chars)
            return self._truncate("嗯，这是个好问题。不过我目前只能基于对话来理解，不太确定具体情境呢。", max_chars)

        # 10. 有视觉上下文时的自然回应
        if vis_present and self.persona.allow_visual_comment and self._turn_count <= 3:
            return self._truncate("你说话的时候我看到你了，继续说吧，我在听。", max_chars)

        # 11. 通用自然回应
        return self._random_natural_reply(text, max_chars)

    def _is_visual_question(self, text: str) -> bool:
        keywords = ["看到", "看见", "画面", "镜头", "摄像头", "你在看", "能看到", "看得见",
                     "看到什么", "你看到", "你看见", "看看", "照照", "拍到了"]
        return any(k in text for k in keywords)

    def _is_status_question(self, text: str) -> bool:
        keywords = ["系统", "状态", "运行", "开了", "关了", "摄像头状态", "麦克风状态",
                     "语音状态", "能不能用", "好不好使"]
        return any(k in text for k in keywords)

    def _is_identity_question(self, text: str) -> bool:
        keywords = ["你是谁", "你的名字", "你是", "叫什么", "你是什么", "你是AI", "你是人"]
        return any(k in text for k in keywords)

    def _is_emotional(self, text: str) -> bool:
        keywords = ["好累", "好烦", "难过", "伤心", "不开心", "好开心", "好高兴",
                     "郁闷", "焦虑", "紧张", "兴奋"]
        return any(k in text for k in keywords)

    def _build_status_reply(self, visual_context: str, max_chars: int) -> str:
        parts = []
        if "检测到用户" in visual_context or "用户在镜头前" in visual_context:
            parts.append("现在能看到画面，你在镜头前。")
        elif "未检测到用户" in visual_context:
            parts.append("现在摄像头开着，但没看到人。")
        elif "不可用" in visual_context or "过暗" in visual_context or "模糊" in visual_context:
            parts.append("现在画面不太清楚。")
        else:
            parts.append("摄像头目前还没打开，或者画面状态不确定。")
        parts.append("语音系统默认是mock模式。")
        return self._truncate(" ".join(parts), max_chars)

    def _get_hour(self) -> int:
        import datetime
        return datetime.datetime.now().hour

    def _random_natural_reply(self, user_text: str, max_chars: int) -> str:
        replies = [
            "嗯，了解了。",
            "有道理呢。",
            "我觉得挺好的。",
            "你说得有道理。",
            "嗯嗯，继续说吧，我在听。",
            "原来如此。",
            "好呀，你有什么想聊的尽管说。",
            "我明白了。",
            "听起来不错。",
        ]
        import random
        return self._truncate(random.choice(replies), max_chars)

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 1] + "…"


class MediaSession:
    """媒体会话管理器"""

    def __init__(self, persona_id: str = "", persona_config: Optional[dict] = None):
        self.persona_id = persona_id
        self.state = SessionState.IDLE
        self.stats = SessionStats()
        self._turns: List[VideoTurn] = []
        self._turn_counter: int = 0
        self._state_listeners: list = []
        self._error_count: int = 0

        self.persona = self._build_persona(persona_id, persona_config)
        self.dialogue_engine = LocalVTuberEngine(self.persona)

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

    def _build_persona(self, persona_id: str, persona_config: Optional[dict]) -> PersonaContext:
        """从 config 构建 PersonaContext，config 值覆盖默认值"""
        pc = persona_config or {}
        return PersonaContext(
            persona_id=persona_id,
            persona_name=pc.get("name", "Mio"),
            display_name=pc.get("display_name", "澪"),
            language=pc.get("language", "zh"),
            speaking_style=pc.get("style", "自然、简短、温和、稍微冷静"),
            max_reply_chars=int(pc.get("max_reply_chars", 100)),
            allow_visual_comment=bool(pc.get("allow_visual_comment", True)),
            avoid_fake_memory=bool(pc.get("avoid_fake_memory", True)),
        )

    async def start(self):
        logger.info("Starting media session for persona=%s", self.persona_id)
        self.state = SessionState.CONNECTING
        self.stats = SessionStats(start_time=time.time())
        self._turns.clear()
        self._turn_counter = 0
        self._conversation_history.clear()
        self._error_count = 0

        if self.mnemosyne_client and self.mnemosyne_client.is_connected():
            try:
                ctx = await self.mnemosyne_client.get_session_context(self.persona_id)
                if ctx:
                    self.persona = PersonaContext(
                        persona_id=ctx.persona_id or self.persona.persona_id,
                        persona_name=ctx.persona_name or self.persona.persona_name,
                        display_name=self.persona.display_name,
                        speaking_style=ctx.speaking_style or self.persona.speaking_style,
                        relationship=ctx.relationship_status or self.persona.relationship,
                        recent_summary=ctx.recent_summary or "",
                        boundaries=ctx.boundaries or [],
                        max_reply_chars=self.persona.max_reply_chars,
                        allow_visual_comment=self.persona.allow_visual_comment,
                        avoid_fake_memory=self.persona.avoid_fake_memory,
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
        logger.info("Media session active (mode=standalone_ai_vtuber)")

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

        # 1. 本地 VTuber 引擎生成回复（主路径）
        llm_start = time.time()
        history_text = "\n".join(self._conversation_history[-6:])
        ai_response = await self.dialogue_engine.generate_response(
            speech_text, visual_context, history_text
        )
        llm_ms = int((time.time() - llm_start) * 1000)
        reply_source = "local_vtuber"
        logger.info("Local VTuber reply: %s...", ai_response[:40])

        # 2. 可选：legacy bridge 覆写（仅当 bridge 启用且已连接）
        if self.mnemosyne_client and self.mnemosyne_client.is_connected():
            try:
                turn_payload = {
                    "persona_id": self.persona_id,
                    "user_text": speech_text,
                    "visual_observation": self._latest_observation,
                    "visual_context": visual_context,
                    "session_id": f"video-companion-{id(self)}",
                    "turn_index": self._turn_counter + 1,
                }
                bridge_response = await self.mnemosyne_client.post_video_turn(turn_payload)
                if bridge_response and bridge_response.reply_text:
                    ai_response = bridge_response.reply_text
                    reply_source = "legacy_bridge"
                    logger.info("Legacy bridge reply: %s...", ai_response[:40])
            except Exception as e:
                logger.debug("Legacy bridge unavailable: %s", e)

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
        persona_cfg = self.persona
        session_id = f"vc-session-{id(self)}"

        # 规则生成 summary_text
        summary_parts = []
        if self._conversation_history:
            user_msgs = [h[6:] for h in self._conversation_history if h.startswith("User: ")]
            if user_msgs:
                sample = user_msgs[-min(3, len(user_msgs)):]
                summary_parts.append(f"用户说了：{'、'.join(sample)}")
        if self.stats.total_vision_frames > 0:
            summary_parts.append(f"收到 {self.stats.total_vision_frames} 帧画面")
        if self.stats.total_external_analyses > 0:
            summary_parts.append(f"调用了 {self.stats.total_external_analyses} 次外部视觉分析")
        if self._latest_observation:
            ps = self._latest_observation.get("presence_status", "unknown")
            summary_parts.append(f"最后视觉状态: {ps}")

        summary_text = "本次会话" + ("、".join(summary_parts) if summary_parts else "暂无记录") + "。"
        topics = self._extract_topics()

        return {
            "session_id": session_id,
            "persona_name": persona_cfg.persona_name,
            "display_name": persona_cfg.display_name,
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
            "reply_mode": "standalone_ai_vtuber",
            "summary_text": summary_text,
            "key_topics": topics,
            "visual_notes": [],
            "system_notes": ["standalone_ai_vtuber_mode"],
            "saved_locally": False,
            "key_facts": [],
            "memory_candidates": [],
            "risk_flags": [],
        }

    def _extract_topics(self) -> list:
        topics = []
        keyword_map = {
            "天气": ["天气", "下雨", "晴天", "热", "冷"],
            "问候": ["你好", "早上", "晚上", "嗨"],
            "系统状态": ["状态", "摄像头", "麦克风", "系统"],
            "视觉": ["看到", "画面", "镜头"],
        }
        for topic, keywords in keyword_map.items():
            for line in self._conversation_history:
                if any(k in line for k in keywords):
                    if topic not in topics:
                        topics.append(topic)
        return topics

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
