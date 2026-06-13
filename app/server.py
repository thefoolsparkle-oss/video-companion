"""
Video Companion 主服务入口

AI VTuber 项目的实时感知与互动核心。
负责：摄像头观察、麦克风输入、ASR、TTS、本地视觉观察、
     本地角色对话、短期会话上下文、会话状态管理、隐私与授权控制。

独立运行，不依赖 Project Mnemosyne / 忆界树。
"""

import asyncio
import logging
import os
import json
import time
import base64
from pathlib import Path
from typing import Optional, Set

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from .consent import ConsentManager, ConsentItem
from .media_session import MediaSession, SessionState, VideoTurn
from .camera_source import CameraSource, CameraConfig
from .audio_source import AudioSource, AudioConfig
from .local_vision import LocalVisionDetector, VideoObservation
from .vision_provider import VisionProviderManager, VisionProviderConfig
from .speech_provider import SpeechProviderManager, SpeechConfig
from .mnemosyne_client import MnemosyneClient, MnemosyneConfig
from .avatar_state import AvatarState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("video-companion")

# 默认配置 — 独立 AI VTuber 模式
DEFAULT_CONFIG = {
    "project": {"mode": "standalone_ai_vtuber", "name": "Video Companion", "description": "AI VTuber realtime perception and interaction core"},
    "server": {"host": "127.0.0.1", "port": 8001, "cors_origins": ["http://localhost:8001"]},
    "camera": {"width": 640, "height": 480, "fps": 15, "capture_interval_sec": 2.0, "default_on": False},
    "microphone": {"sample_rate": 16000, "chunk_size": 1024, "default_on": False},
    "local_vision": {"detection_interval_sec": 1.0, "enabled_detectors": ["face", "motion"], "face_confidence": 0.5, "motion_sensitivity": 0.3},
    "vision_provider": {"provider": "mock", "model": "gpt-4o", "max_frames_per_minute": 6, "max_cost_per_hour": 0.5, "max_cost_per_day": 2.0, "max_resolution": 1024, "fallback_on_limit": "skip", "api_key_env": "OPENAI_API_KEY", "api_base": "https://api.openai.com/v1", "default_on": False},
    "speech": {"asr": {"provider": "mock", "model": "whisper-1", "language": "zh"}, "tts": {"provider": "mock", "model": "tts-1", "voice": "alloy", "speed": 1.0, "streaming": True, "interruptible": True}, "api_key_env": "OPENAI_API_KEY"},
    "legacy_bridge": {"api_base": "http://127.0.0.1:8000", "api_key_env": "MNEMOSYNE_API_KEY", "timeout": 10, "retries": 2, "enabled": False},
    "persona": {"name": "Mio", "display_name": "澪", "language": "zh", "style": "自然、简短、温和、稍微冷静", "max_reply_chars": 100, "allow_visual_comment": True, "avoid_fake_memory": True},
    "privacy": {"defaults": {"camera": False, "microphone": False, "external_vision": False, "save_summary": False, "save_observation": False}, "save_raw_media": False, "log_redact_pii": True, "camera_default": False, "microphone_default": False, "external_vision_default": False},
    "cost": {"max_frames_per_minute": 6, "max_cost_per_hour": 0.5, "max_cost_per_day": 2.0, "on_limit": "skip"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个 dict"""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


class VideoCompanionServer:
    """视频陪伴服务主类"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.consent = ConsentManager(
            defaults=self.config.get("privacy", {}).get("defaults", {}),
            redact_pii=self.config.get("privacy", {}).get("log_redact_pii", True),
        )
        self.media_session: Optional[MediaSession] = None

        # 各子模块
        cam_cfg = self.config.get("camera", {})
        self.camera = CameraSource(CameraConfig(
            width=cam_cfg.get("default_width", cam_cfg.get("width", 640)),
            height=cam_cfg.get("default_height", cam_cfg.get("height", 480)),
            fps=cam_cfg.get("default_fps", cam_cfg.get("fps", 15)),
            capture_interval_sec=cam_cfg.get("capture_interval_sec", 2.0),
            default_on=cam_cfg.get("default_on", False),
        ))

        mic_cfg = self.config.get("microphone", {})
        self.audio = AudioSource(AudioConfig(
            sample_rate=mic_cfg.get("sample_rate", 16000),
            chunk_size=mic_cfg.get("chunk_size", 1024),
            default_on=mic_cfg.get("default_on", False),
        ))

        self.local_vision = LocalVisionDetector(
            config=self.config.get("local_vision", {})
        )

        vp_cfg = self.config.get("vision_provider", {})
        self.vision = VisionProviderManager(
            config=VisionProviderConfig(
                provider=vp_cfg.get("provider", "mock"),
                model=vp_cfg.get("model", "gpt-4o"),
                max_frames_per_minute=vp_cfg.get("max_frames_per_minute", 6),
                max_cost_per_hour=vp_cfg.get("max_cost_per_hour", 0.5),
                max_cost_per_day=vp_cfg.get("max_cost_per_day", 2.0),
                max_resolution=vp_cfg.get("max_resolution", 1024),
                fallback_on_limit=vp_cfg.get("fallback_on_limit", "skip"),
                api_key_env=vp_cfg.get("api_key_env", "OPENAI_API_KEY"),
                api_base=vp_cfg.get("api_base", "https://api.openai.com/v1"),
            ),
            enabled=vp_cfg.get("default_on", False),
        )

        sp_cfg = self.config.get("speech", {})
        self.speech = SpeechProviderManager(SpeechConfig(
            asr_provider=sp_cfg.get("asr", {}).get("provider", "mock"),
            asr_model=sp_cfg.get("asr", {}).get("model", "whisper-1"),
            asr_language=sp_cfg.get("asr", {}).get("language", "zh"),
            tts_provider=sp_cfg.get("tts", {}).get("provider", "mock"),
            tts_model=sp_cfg.get("tts", {}).get("model", "tts-1"),
            tts_voice=sp_cfg.get("tts", {}).get("voice", "alloy"),
            tts_speed=sp_cfg.get("tts", {}).get("speed", 1.0),
            tts_streaming=sp_cfg.get("tts", {}).get("streaming", True),
            api_key_env=sp_cfg.get("api_key_env", "OPENAI_API_KEY"),
        ))

        lb_cfg = self.config.get("legacy_bridge", self.config.get("mnemosyne", {}))
        self.mnemosyne = MnemosyneClient(MnemosyneConfig(
            api_base=lb_cfg.get("api_base", "http://127.0.0.1:8000"),
            api_key_env=lb_cfg.get("api_key_env", "MNEMOSYNE_API_KEY"),
            timeout=lb_cfg.get("timeout", 10),
            retries=lb_cfg.get("retries", 2),
            enabled=lb_cfg.get("enabled", False),
        ))

        self._active_ws: Set[WebSocket] = set()
        self._server_start_time: float = time.time()
        self._reconnect_task: Optional[asyncio.Task] = None

    def _load_config(self, config_path: str) -> dict:
        if not os.path.exists(config_path):
            logger.warning("Config file %s not found, using defaults", config_path)
            return DEFAULT_CONFIG

        if HAS_YAML:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = yaml.safe_load(f) or {}
            return _deep_merge(DEFAULT_CONFIG, file_config)
        else:
            return DEFAULT_CONFIG

    async def initialize(self):
        logger.info("=" * 50)
        logger.info("Video Companion Server initializing...")
        await self.local_vision.initialize()
        await self.vision.initialize()
        await self.speech.initialize()
        await self.mnemosyne.initialize()
        # 仅在 legacy bridge 启用时启动重连轮询
        if self.mnemosyne.config.enabled:
            self._reconnect_task = asyncio.create_task(self._mnemosyne_reconnect_loop())
            logger.info("Legacy bridge reconnect loop started")
        logger.info("All modules initialized")
        logger.info("=" * 50)

    async def _mnemosyne_reconnect_loop(self):
        """后台轮询 legacy bridge 重连，每 30 秒尝试一次"""
        while True:
            await asyncio.sleep(30)
            if not self.mnemosyne.is_connected():
                try:
                    await self.mnemosyne.reconnect()
                except Exception:
                    pass

    async def start_session(self, persona_id: str = "default") -> MediaSession:
        if self.media_session and self.media_session.is_active():
            await self.media_session.stop()

        persona_config = self.config.get("persona", {})
        self.media_session = MediaSession(persona_id=persona_id, persona_config=persona_config)
        self.media_session.camera_source = self.camera
        self.media_session.audio_source = self.audio
        self.media_session.local_vision = self.local_vision
        self.media_session.vision_provider = self.vision
        self.media_session.speech_provider = self.speech
        self.media_session.consent_manager = self.consent
        self.media_session.mnemosyne_client = self.mnemosyne

        await self.media_session.start()
        return self.media_session

    async def stop_session(self) -> dict:
        if not self.media_session:
            return {}
        return await self.media_session.stop()

    # ---- WebSocket 消息处理 ----

    async def handle_ws_message(self, ws: WebSocket, data: dict):
        """处理 WebSocket 消息分发"""
        msg_type = data.get("type", "")

        if msg_type == "ping":
            await ws.send_json({"type": "pong", "timestamp": time.time()})

        elif msg_type == "frame":
            await self._handle_frame(ws, data)

        elif msg_type == "speech_input":
            await self._handle_speech(ws, data)

        elif msg_type == "text_input":
            await self._handle_text(ws, data)

        elif msg_type == "interrupt":
            await self._handle_interrupt(ws)

        elif msg_type == "consent_update":
            await self._handle_consent_ws(ws, data)

        elif msg_type == "get_status":
            await ws.send_json({
                "type": "status",
                "data": self.get_system_status()
            })

        else:
            await ws.send_json({
                "type": "error",
                "message": f"Unknown message type: {msg_type}"
            })

    async def _handle_frame(self, ws: WebSocket, data: dict):
        """处理视频帧"""
        frame_data = data.get("data", "")
        if not frame_data:
            return

        # 接收帧
        frame = self.camera.receive_frame(
            data_base64=frame_data,
            width=data.get("width", 640),
            height=data.get("height", 480),
            format=data.get("format", "jpeg"),
        )

        if frame is None:
            return

        # 本地视觉检测
        t0 = time.time()
        observation = await self.local_vision.detect(
            data_base64=frame_data,
            width=frame.width,
            height=frame.height,
            timestamp=frame.timestamp,
        )
        vision_latency = int((time.time() - t0) * 1000)

        # 更新会话
        if self.media_session and self.media_session.is_active():
            self.media_session.update_observation(observation.to_dict())

        # 外部视觉模型分析（如果已授权且满足频率限制）
        external_result = None
        if self.consent.can_upload_to_vision_model() and self.vision.enabled:
            t1 = time.time()
            safe_content = self._check_safe_content(observation)
            if safe_content:
                external_result = await self.vision.analyze_frame(
                    image_base64=frame_data,
                    prompt="请简要描述画面：是否有人、在做什么、情绪、物品。中文，60字内。",
                    max_tokens=80,
                )
                if external_result and not external_result.error:
                    observation.external_analysis = True
                    observation.external_description = external_result.description
                    if self.media_session:
                        self.media_session.stats.total_external_analyses += 1
            ext_latency = int((time.time() - t1) * 1000) if external_result else 0

        # 推送给前端
        payload = {
            "type": "observation",
            "data": observation.to_dict(),
        }
        if external_result and not external_result.error:
            payload["external"] = external_result.to_dict()
        await ws.send_json(payload)

    async def _handle_speech(self, ws: WebSocket, data: dict):
        """处理语音输入"""
        audio_data = data.get("data", "")
        if not audio_data:
            return

        # 接收音频并累积到缓冲区
        chunk = self.audio.receive_audio(
            data_base64=audio_data,
            duration_ms=data.get("duration_ms", 200),
            sample_rate=data.get("sample_rate", 16000),
        )

        # 检查是否结束说话（VAD 检测到静音区间）
        vad_ended = data.get("vad_ended", False)
        vad_text = data.get("vad_text", "").strip()

        if not vad_ended:
            return  # 仍在说话，继续累积

        # 用户说完了一段话 —— 确定用什么文本
        speech_text = ""
        asr_source = "unknown"

        if vad_text:
            # 浏览器端 SpeechRecognition 提供了文本（低成本辅助路径）
            speech_text = vad_text
            asr_source = "browser_asr"

        else:
            # 没有浏览器端识别结果 —— 调用后端 ASR
            audio_bytes = self.audio.get_accumulated_audio_bytes()

            if not audio_bytes:
                await ws.send_json({
                    "type": "system_error",
                    "code": "asr_no_audio",
                    "message": "未收到有效音频数据，无法识别语音。",
                })
                self.audio.clear_buffer()
                return

            try:
                transcript = await self.speech.transcribe(audio_bytes)
            except Exception as e:
                logger.error("ASR exception: %s", e)
                transcript = None

            if transcript and transcript.text and not transcript.error:
                speech_text = transcript.text
                asr_source = "backend_asr"
                logger.info("ASR result (confidence=%.2f): %s",
                            transcript.confidence, speech_text[:60])
            else:
                err_msg = transcript.error if transcript else "ASR 服务不可用"
                await ws.send_json({
                    "type": "system_error",
                    "code": "asr_failed",
                    "message": f"语音识别失败：{err_msg}",
                })
                self.audio.clear_buffer()
                return

        # 清理音频缓冲区（无论走哪条路径，一旦处理就清空）
        self.audio.clear_buffer()

        # 进入对话处理
        await self._process_speech_turn(
            ws, speech_text,
            confidence=data.get("confidence", 0.0),
            asr_source=asr_source,
        )

    async def _handle_text(self, ws: WebSocket, data: dict):
        """处理文本输入（键盘输入回退）"""
        text = data.get("text", "").strip()
        if not text:
            return
        await self._process_speech_turn(ws, text, 1.0, asr_source="text_input")

    async def _process_speech_turn(self, ws: WebSocket, text: str,
                                   confidence: float = 0.0,
                                   asr_source: str = "unknown"):
        """处理一轮完整语音对话"""
        if not self.media_session or not self.media_session.is_active():
            await ws.send_json({
                "type": "system_error",
                "code": "no_session",
                "message": "没有活动中的会话。请先开始会话。"
            })
            return

        t0 = time.time()

        try:
            # 1. 生成 AI 回复（含视觉上下文）
            turn = await self.media_session.process_user_speech(
                speech_text=text,
                speech_confidence=confidence,
                asr_latency_ms=0,
            )

            # 2. TTS 合成
            tts_result = await self.media_session.process_tts_and_respond(turn)

            total_latency = int((time.time() - t0) * 1000)

            # 3. 发送回复给前端
            obs = self.media_session.get_latest_observation()
            avatar_state = AvatarState.from_visual_state(
                presence_status=obs.get("presence_status", "unknown") if obs else "unknown",
                face_mood=obs.get("face", {}).get("rough_mood") if obs else None,
                motion_level=obs.get("motion", {}).get("level", "still") if obs else "still",
            )
            if turn.ai_response_text:
                avatar_state.mouth_open = True
                avatar_state.speaking = True
                avatar_state.expression = "talking"

            response = {
                "type": "ai_response",
                "turn_id": turn.turn_id,
                "text": turn.ai_response_text,
                "audio_base64": tts_result.audio_base64 if tts_result and not tts_result.error else "",
                "audio_format": tts_result.format if tts_result else "mp3",
                "total_latency_ms": total_latency,
                "visual_context": turn.visual_context,
                "asr_source": asr_source,
                "reply_source": turn.reply_source,
                "avatar_state": avatar_state.to_dict(),
            }
            await ws.send_json(response)

            # 4. 记录对话
            await ws.send_json({
                "type": "transcript",
                "turn_id": turn.turn_id,
                "speaker": "user",
                "text": text,
            })
            await ws.send_json({
                "type": "transcript",
                "turn_id": turn.turn_id,
                "speaker": "ai",
                "text": turn.ai_response_text,
            })

            # 5. 重要观察回写 legacy bridge（可选）
            if (self.consent.can_save_observation() and
                self.media_session.get_latest_observation() and
                self.mnemosyne.is_connected()):
                obs = self.media_session.get_latest_observation()
                if obs.get("external_analysis"):
                    asyncio.create_task(
                        self.mnemosyne.post_observation(obs)
                    )

        except Exception as e:
            logger.error("Speech turn processing error: %s", e)
            if self.media_session:
                self.media_session.stats.errors += 1
            await ws.send_json({
                "type": "system_error",
                "code": "turn_failed",
                "message": f"处理失败: {str(e)[:100]}"
            })

    async def _handle_interrupt(self, ws: WebSocket):
        """打断播放"""
        if self.media_session:
            self.media_session.interrupt()
        self.speech.interrupt()
        await self.audio.interrupt()
        await ws.send_json({"type": "interrupted"})
        # 广播给所有连接
        for w in self._active_ws:
            if w != ws:
                try:
                    await w.send_json({"type": "interrupted"})
                except Exception:
                    pass

    async def _handle_consent_ws(self, ws: WebSocket, data: dict):
        """WebSocket 授权变更 — 统一经过 ConsentManager 公开方法"""
        item = data.get("item", "")
        granted = data.get("granted", False)
        reason = data.get("reason", "ws_client")

        if not item:
            return

        # 映射到 ConsentManager 公开方法（统一入口，经过审计）
        item_methods = {
            "camera": (self.consent.grant_camera, self.consent.revoke_camera),
            "microphone": (self.consent.grant_microphone, self.consent.revoke_microphone),
            "external_vision": (self.consent.grant_external_vision, self.consent.revoke_external_vision),
        }

        if item not in item_methods:
            await ws.send_json({"type": "error", "message": f"Unknown consent item: {item}"})
            return

        grant_fn, revoke_fn = item_methods[item]
        if granted:
            grant_fn(reason=reason)
        else:
            revoke_fn(reason=reason)

        # 硬件联动
        if item == "camera":
            if granted:
                await self.camera.start()
            else:
                await self.camera.stop()
        elif item == "microphone":
            if granted:
                await self.audio.start_listening()
            else:
                await self.audio.stop_listening()
        elif item == "external_vision":
            self.vision.set_enabled(granted)

        # 广播最新状态
        await ws.send_json({
            "type": "consent_changed",
            "item": item,
            "granted": granted,
            "state": self.consent.to_dict(),
        })

    def _check_safe_content(self, observation: VideoObservation) -> bool:
        """检查画面是否适合上传外部模型（V7 隐私硬化）"""
        if not observation.is_usable:
            return False
        if observation.brightness < 0.02:
            return False  # 太暗，可能没画面或隐私场景
        return True

    # ---- 状态查询 ----

    def get_consent_state(self) -> dict:
        return self.consent.to_dict()

    def get_system_status(self) -> dict:
        session_state = (
            self.media_session.get_state().value
            if self.media_session else SessionState.IDLE.value
        )
        duration = (
            self.media_session.stats.duration_sec
            if self.media_session else 0.0
        )
        turns = (
            self.media_session.stats.total_turns
            if self.media_session else 0
        )

        return {
            "service": "Video Companion",
            "version": "0.3.0-dev",
            "project_mode": "standalone_ai_vtuber",
            "uptime_sec": round(time.time() - self._server_start_time, 1),
            "session_state": session_state,
            "duration_sec": round(duration, 1),
            "total_turns": turns,
            "consent": self.consent.to_dict(),
            "camera_metrics": self.camera.get_metrics(),
            "audio_metrics": self.audio.get_metrics(),
            "vision_usage": self.vision.get_usage_stats(),
            "speech_stats": self.speech.get_stats(),
            "mnemosyne": self.mnemosyne.get_stats(),
            "ws_connections": len(self._active_ws),
        }


# ============ FastAPI 应用构建 ============

def create_app(server: VideoCompanionServer) -> FastAPI:
    if not HAS_FASTAPI:
        raise RuntimeError("fastapi required: pip install fastapi uvicorn")

    app = FastAPI(
        title="Video Companion",
        version="0.3.0-dev",
        description="AI VTuber 实时感知与互动核心 — 独立运行",
    )

    cors_origins = server.config.get("server", {}).get("cors_origins", ["*"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    web_dir = Path(__file__).parent.parent / "web"
    if web_dir.exists():
        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    # ---- REST API ----

    @app.get("/")
    async def root():
        if web_dir.exists():
            index_path = web_dir / "index.html"
            if index_path.exists():
                return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return {"service": "Video Companion", "version": "0.3.0-dev", "project_mode": "standalone_ai_vtuber", "docs": "/docs"}

    @app.get("/api/status")
    async def get_status():
        return server.get_system_status()

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/consent")
    async def get_consent():
        return server.get_consent_state()

    @app.post("/api/consent/{item}/grant")
    async def grant_consent(item: str):
        if item == "camera":
            server.consent.grant_camera(reason="rest_api")
            await server.camera.start()
        elif item == "microphone":
            server.consent.grant_microphone(reason="rest_api")
            await server.audio.start_listening()
        elif item == "external_vision":
            server.consent.grant_external_vision(reason="rest_api")
            server.vision.set_enabled(True)
        else:
            return JSONResponse({"error": f"Unknown consent item: {item}"}, status_code=400)
        return {"status": "granted", "item": item}

    @app.post("/api/consent/{item}/revoke")
    async def revoke_consent(item: str):
        if item == "camera":
            server.consent.revoke_camera(reason="rest_api")
            await server.camera.stop()
        elif item == "microphone":
            server.consent.revoke_microphone(reason="rest_api")
            await server.audio.stop_listening()
        elif item == "external_vision":
            server.consent.revoke_external_vision(reason="rest_api")
            server.vision.set_enabled(False)
        else:
            return JSONResponse({"error": f"Unknown consent item: {item}"}, status_code=400)
        return {"status": "revoked", "item": item}

    @app.post("/api/consent/revoke-all")
    async def revoke_all_consent():
        server.consent.revoke_all(reason="api_revoke_all")
        await server.camera.stop()
        await server.audio.stop_listening()
        if server.speech:
            server.speech.interrupt()
        server.vision.set_enabled(False)
        return {"status": "all_revoked"}

    @app.get("/api/consent/audit")
    async def get_consent_audit(limit: int = 50):
        return server.consent.get_audit_log(limit)

    @app.post("/api/session/start")
    async def start_session(persona_id: str = "default"):
        session = await server.start_session(persona_id)
        return {
            "status": "started",
            "session_state": session.get_state().value,
            "persona_id": persona_id,
        }

    @app.post("/api/session/stop")
    async def stop_session():
        # 停止媒体采集
        await server.camera.stop()
        await server.audio.stop_listening()
        # 中断 TTS 播放
        if server.speech:
            server.speech.interrupt()
        # 停用外部视觉上传
        server.vision.set_enabled(False)
        # 撤销媒体相关授权
        server.consent.revoke_camera(reason="session_stop")
        server.consent.revoke_microphone(reason="session_stop")
        server.consent.revoke_external_vision(reason="session_stop")
        # 停止会话（生成摘要、回写 legacy bridge）
        summary = await server.stop_session()
        return {
            "status": "stopped",
            "summary": summary,
            "consent": server.consent.to_dict(),
        }

    @app.get("/api/session/status")
    async def session_status():
        if not server.media_session:
            return {"session_state": SessionState.IDLE.value}
        s = server.media_session
        return {
            "session_state": s.get_state().value,
            "persona_id": s.persona_id,
            "total_turns": s.stats.total_turns,
            "duration_sec": round(s.stats.duration_sec, 1),
            "latest_observation": s.get_latest_observation(),
        }

    @app.get("/api/session/turns")
    async def get_turns(limit: int = 20):
        if not server.media_session:
            return []
        return [t.to_dict() for t in server.media_session.get_turns(limit)]

    @app.get("/api/session/history")
    async def get_dialogue_history(limit: int = 10):
        if not server.media_session:
            return {"history": ""}
        return {"history": server.media_session.get_conversation_history(limit)}

    @app.get("/api/camera/metrics")
    async def camera_metrics():
        return server.camera.get_metrics()

    @app.get("/api/audio/metrics")
    async def audio_metrics():
        return server.audio.get_metrics()

    @app.get("/api/vision/usage")
    async def vision_usage():
        return server.vision.get_usage_stats()

    # ---- WebSocket ----

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        server._active_ws.add(ws)
        logger.info("WebSocket client connected (total=%d)", len(server._active_ws))

        # 发送当前状态
        await ws.send_json({
            "type": "status",
            "data": server.get_system_status()
        })

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue
                await server.handle_ws_message(ws, data)

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)
        finally:
            server._active_ws.discard(ws)
            logger.info("WebSocket disconnected (total=%d)", len(server._active_ws))

    @app.on_event("startup")
    async def on_startup():
        await server.initialize()

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Server shutting down...")
        if server._reconnect_task:
            server._reconnect_task.cancel()
        if server.media_session and server.media_session.is_active():
            await server.media_session.stop()
        await server.mnemosyne.close()
        logger.info("Server shutdown complete")

    return app


async def main():
    import uvicorn

    config_path = os.environ.get("VC_CONFIG", "config.yaml")
    server = VideoCompanionServer(config_path=config_path)
    app = create_app(server)

    server_cfg = server.config.get("server", {})
    host = server_cfg.get("host", "127.0.0.1")
    port = int(server_cfg.get("port", 8001))

    logger.info("Starting Video Companion on http://%s:%d", host, port)
    uvicorn_config = uvicorn.Config(app, host=host, port=port, log_level="info")
    uvicorn_server = uvicorn.Server(uvicorn_config)
    await uvicorn_server.serve()


if __name__ == "__main__":
    asyncio.run(main())
