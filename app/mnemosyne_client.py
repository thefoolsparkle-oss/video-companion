"""
主项目 (Project Mnemosyne) API 客户端 (V6 完善版)

通过 HTTP API 与 Project Mnemosyne 通信。
实现完整的主项目桥接：
- 拉取人格会话上下文
- 回写会话摘要
- 回写视觉观察
- 同步授权状态
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import logging
import os
import json

logger = logging.getLogger(__name__)

# 尝试导入异步 HTTP 客户端
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


@dataclass
class MnemosyneConfig:
    api_base: str = "http://127.0.0.1:8000"
    api_key_env: str = "MNEMOSYNE_API_KEY"
    timeout: int = 10
    retries: int = 2
    enabled: bool = True


@dataclass
class SessionContext:
    """视频会话启动上下文"""
    persona_id: str = ""
    persona_name: str = ""
    persona_public_info: Dict[str, Any] = field(default_factory=dict)
    speaking_style: str = "casual"
    relationship_status: str = "acquaintance"
    recent_summary: str = ""
    boundaries: List[str] = field(default_factory=list)
    consent_state: Dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: dict) -> "SessionContext":
        return cls(
            persona_id=data.get("persona_id", ""),
            persona_name=data.get("persona_name", ""),
            persona_public_info=data.get("persona_public_info", {}),
            speaking_style=data.get("speaking_style", "casual"),
            relationship_status=data.get("relationship_status", "acquaintance"),
            recent_summary=data.get("recent_summary", ""),
            boundaries=data.get("boundaries", []),
            consent_state=data.get("consent_state", {}),
        )


@dataclass
class SessionSummaryPayload:
    """回写主项目的会话摘要"""
    persona_id: str
    start_time: str
    end_time: str
    key_facts: List[str] = field(default_factory=list)
    memory_candidates: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    session_duration_sec: int = 0
    total_turns: int = 0

    def to_dict(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "key_facts": self.key_facts,
            "memory_candidates": self.memory_candidates,
            "risk_flags": self.risk_flags,
            "session_duration_sec": self.session_duration_sec,
            "total_turns": self.total_turns,
        }


@dataclass
class VideoTurnResponse:
    """主项目对视频 turn 的回复"""
    reply_text: str = ""
    voice_style: str = "natural"
    expression: str = "neutral"
    memory_policy: Dict[str, Any] = field(default_factory=lambda: {
        "should_extract": False,
        "candidate_only": True,
    })
    error: Optional[str] = None

    @classmethod
    def from_api_response(cls, data: dict) -> "VideoTurnResponse":
        return cls(
            reply_text=data.get("reply_text", ""),
            voice_style=data.get("voice_style", "natural"),
            expression=data.get("expression", "neutral"),
            memory_policy=data.get("memory_policy", {}),
        )


class MnemosyneClient:
    """主项目 API 客户端"""

    def __init__(self, config: Optional[MnemosyneConfig] = None):
        self.config = config or MnemosyneConfig()
        self._http_client = None
        self._connected: bool = False
        self._api_key: str = ""
        self._request_count: int = 0
        self._error_count: int = 0

    async def initialize(self):
        """初始化 HTTP 客户端"""
        self._api_key = os.environ.get(self.config.api_key_env, "")

        if not self.config.enabled:
            logger.info("Mnemosyne bridge: DISABLED")
            return

        logger.info("Mnemosyne bridge initializing (api_base=%s)", self.config.api_base)

        if HAS_HTTPX:
            self._http_client = httpx.AsyncClient(
                base_url=self.config.api_base,
                timeout=self.config.timeout,
                headers=self._build_headers(),
            )
        elif HAS_AIOHTTP:
            self._http_client = None  # 使用 aiohttp 方式
        else:
            logger.warning("No HTTP client available (install httpx or aiohttp)")

        # 测试连接
        self._connected = await self._try_connect()
        if self._connected:
            logger.info("Mnemosyne bridge: CONNECTED")
        else:
            logger.info("Mnemosyne bridge: UNREACHABLE (will work in offline mode)")

    def _build_headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _request(self, method: str, path: str,
                       json_data: Optional[dict] = None,
                       params: Optional[dict] = None) -> Optional[dict]:
        """发起 HTTP 请求"""
        if not self.config.enabled:
            return None
        if not self._http_client and not HAS_HTTPX:
            return None

        self._request_count += 1
        url = f"{self.config.api_base}{path}"

        for attempt in range(self.config.retries + 1):
            try:
                if HAS_HTTPX and self._http_client:
                    resp = await self._http_client.request(
                        method, path, json=json_data, params=params
                    )
                    if resp.status_code < 500:
                        return resp.json() if resp.content else {}
                    logger.warning("Mnemosyne API %s %s -> %d (attempt %d)",
                                   method, path, resp.status_code, attempt + 1)
                else:
                    return await self._aiohttp_request(method, path, json_data, params)
            except Exception as e:
                logger.debug("Mnemosyne request failed (attempt %d): %s",
                             attempt + 1, e)
                if attempt < self.config.retries:
                    import asyncio
                    await asyncio.sleep(1)

        self._error_count += 1
        return None

    async def _aiohttp_request(self, method: str, path: str,
                               json_data: Optional[dict] = None,
                               params: Optional[dict] = None) -> Optional[dict]:
        """aiohttp 后端请求"""
        if not HAS_AIOHTTP:
            return None
        import aiohttp
        url = f"{self.config.api_base}{path}"
        headers = self._build_headers()
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url, json=json_data, params=params,
                headers=headers, timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as resp:
                if resp.status < 500:
                    return await resp.json()
                return None

    async def _try_connect(self) -> bool:
        """尝试建立连接 — 不依赖 GET / 返回 JSON"""
        if not self.config.enabled:
            return False
        try:
            if HAS_HTTPX and self._http_client:
                resp = await self._http_client.get("/api/health", timeout=5)
                return resp.status_code < 500
            elif HAS_AIOHTTP:
                return await self._aiohttp_health_check()
        except Exception:
            pass
        return False

    async def _aiohttp_health_check(self) -> bool:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.api_base}/api/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status < 500
        except Exception:
            return False

    async def health_check(self) -> bool:
        """检查主项目连接 — 使用专用 health 端点"""
        return await self._try_connect()

    async def reconnect(self) -> bool:
        """尝试重新连接主项目"""
        if self._connected:
            return True
        logger.info("Mnemosyne bridge: attempting reconnect...")
        if HAS_HTTPX and not self._http_client:
            try:
                self._http_client = httpx.AsyncClient(
                    base_url=self.config.api_base,
                    timeout=self.config.timeout,
                    headers=self._build_headers(),
                )
            except Exception as e:
                logger.warning("Failed to create HTTP client: %s", e)
                return False
        self._connected = await self._try_connect()
        if self._connected:
            logger.info("Mnemosyne bridge: RECONNECTED")
        return self._connected

    async def get_session_context(self, persona_id: str) -> Optional[SessionContext]:
        """获取视频会话启动上下文

        GET /api/video/session-context?persona_id=...
        """
        logger.info("Fetching session context for persona=%s", persona_id)
        result = await self._request("GET", "/api/video/session-context",
                                     params={"persona_id": persona_id})
        if result:
            return SessionContext.from_api_response(result)

        # 离线回退：返回空上下文
        return SessionContext(persona_id=persona_id)

    async def post_session_summary(self, summary: dict) -> bool:
        """回写会话摘要

        POST /api/video/session-summary
        """
        logger.info("Posting session summary for persona=%s",
                     summary.get("persona_id", "?"))
        payload = SessionSummaryPayload(
            persona_id=summary.get("persona_id", ""),
            start_time=str(summary.get("start_time", "")),
            end_time=str(summary.get("end_time", "")),
            session_duration_sec=int(summary.get("duration_sec", 0)),
            total_turns=summary.get("total_turns", 0),
            key_facts=summary.get("key_facts", []),
            memory_candidates=summary.get("memory_candidates", []),
            risk_flags=summary.get("risk_flags", []),
        )
        result = await self._request(
            "POST", "/api/video/session-summary",
            json_data=payload.to_dict()
        )
        return result is not None

    async def post_observation(self, observation: dict) -> bool:
        """回写重要视觉观察

        POST /api/video/observation
        """
        logger.debug("Posting observation: %s",
                      observation.get("object_hint", ""))
        payload = {
            "timestamp": observation.get("timestamp", 0),
            "description": observation.get("external_description", ""),
            "confidence": observation.get("face", {}).get("confidence", 0),
            "user_present": observation.get("user_present"),
            "presence_status": observation.get("presence_status", "unknown"),
            "object_hint": observation.get("object_hint"),
            "allow_long_term_memory": observation.get("allow_long_term_memory", False),
            "evidence_type": "video_observation",
        }
        result = await self._request(
            "POST", "/api/video/observation", json_data=payload
        )
        return result is not None

    async def sync_consent(self, consent_payload: dict) -> bool:
        """同步用户视频授权状态

        POST /api/video/consent
        """
        logger.info("Syncing consent: camera=%s mic=%s vision=%s",
                     consent_payload.get("camera", False),
                     consent_payload.get("microphone", False),
                     consent_payload.get("external_vision_upload", False))
        result = await self._request(
            "POST", "/api/video/consent", json_data=consent_payload
        )
        return result is not None

    async def post_video_turn(self, turn_payload: dict) -> Optional[VideoTurnResponse]:
        """调用主项目视频 turn 接口

        POST /api/video/turn
        """
        logger.debug("Posting video turn for persona=%s turn=%d",
                      turn_payload.get("persona_id", "?"),
                      turn_payload.get("turn_index", 0))
        result = await self._request(
            "POST", "/api/video/turn", json_data=turn_payload
        )
        if result:
            resp = VideoTurnResponse.from_api_response(result)
            if resp.reply_text:
                logger.info("Main project replied: %s...", resp.reply_text[:40])
            return resp
        return None

    async def close(self):
        """关闭连接"""
        if self._http_client and HAS_HTTPX:
            await self._http_client.aclose()

    def is_connected(self) -> bool:
        return self._connected

    def get_stats(self) -> dict:
        return {
            "api_base": self.config.api_base,
            "connected": self._connected,
            "requests": self._request_count,
            "errors": self._error_count,
        }
