"""
外部视觉模型 Provider 接口 (V3 完善版)

支持可替换的视觉模型 provider，包含：
- OpenAI GPT-4o 视觉分析
- Anthropic Claude 视觉分析
- Mock provider (测试用)
- 频率限制
- 费用估算和上限控制
- 降级策略
- 帧分辨率缩放
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import time
import base64
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class VisionProviderConfig:
    provider: str = "mock"
    model: str = "gpt-4o"
    max_frames_per_minute: int = 6
    max_cost_per_hour: float = 0.5
    max_cost_per_day: float = 2.0
    max_resolution: int = 1024
    fallback_on_limit: str = "skip"
    api_key_env: str = "OPENAI_API_KEY"
    api_base: str = "https://api.openai.com/v1"


@dataclass
class VisionResult:
    """外部视觉模型分析结果"""
    description: str = ""
    objects: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    mood: str = "unknown"
    confidence: float = 0.0
    tokens_used: int = 0
    cost_estimate: float = 0.0
    error: Optional[str] = None
    provider_used: str = ""
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "objects": self.objects,
            "actions": self.actions,
            "mood": self.mood,
            "confidence": self.confidence,
            "tokens_used": self.tokens_used,
            "cost_estimate": self.cost_estimate,
            "error": self.error,
            "provider_used": self.provider_used,
            "latency_ms": self.latency_ms,
        }


class RateLimiter:
    """抽帧频率和费用限制器"""

    def __init__(self, max_frames_per_minute: int = 6,
                 max_cost_per_hour: float = 0.5,
                 max_cost_per_day: float = 2.0):
        self.max_frames_per_minute = max_frames_per_minute
        self.max_cost_per_hour = max_cost_per_hour
        self.max_cost_per_day = max_cost_per_day

        self._frame_timestamps: List[float] = []
        self._hourly_cost: float = 0.0
        self._hour_start: float = time.time()
        self._daily_cost: float = 0.0
        self._day_start: float = time.time()
        self._total_frames: int = 0
        self._total_cost: float = 0.0

    def can_send(self) -> tuple:
        """检查是否可以发送，返回 (allowed, reason)"""
        now = time.time()

        # 清理过期记录
        self._frame_timestamps = [
            t for t in self._frame_timestamps if now - t < 60
        ]
        if now - self._hour_start > 3600:
            self._hourly_cost = 0.0
            self._hour_start = now
        if now - self._day_start > 86400:
            self._daily_cost = 0.0
            self._day_start = now

        # 分钟频率检查
        if len(self._frame_timestamps) >= self.max_frames_per_minute:
            return False, "minute_limit"

        # 小时费用检查
        if self._hourly_cost >= self.max_cost_per_hour:
            return False, "hourly_cost_limit"

        # 日费用检查
        if self._daily_cost >= self.max_cost_per_day:
            return False, "daily_cost_limit"

        return True, "ok"

    def record_send(self, cost: float = 0.0):
        """记录一次发送"""
        now = time.time()
        self._frame_timestamps.append(now)
        self._hourly_cost += cost
        self._daily_cost += cost
        self._total_frames += 1
        self._total_cost += cost

    def get_stats(self) -> dict:
        now = time.time()
        self._frame_timestamps = [
            t for t in self._frame_timestamps if now - t < 60
        ]
        if now - self._hour_start > 3600:
            self._hourly_cost = 0.0
        if now - self._day_start > 86400:
            self._daily_cost = 0.0

        return {
            "frames_this_minute": len(self._frame_timestamps),
            "max_frames_per_minute": self.max_frames_per_minute,
            "cost_this_hour": round(self._hourly_cost, 6),
            "max_cost_per_hour": self.max_cost_per_hour,
            "cost_today": round(self._daily_cost, 6),
            "max_cost_per_day": self.max_cost_per_day,
            "total_frames": self._total_frames,
            "total_cost": round(self._total_cost, 6),
        }


class BaseVisionProvider(ABC):
    """视觉模型 Provider 抽象基类"""

    @abstractmethod
    async def analyze(self, image_base64: str, prompt: Optional[str] = None,
                      max_tokens: int = 150) -> VisionResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class MockVisionProvider(BaseVisionProvider):
    """Mock provider —— 测试用，模拟返回"""

    @property
    def name(self) -> str:
        return "mock"

    async def analyze(self, image_base64: str, prompt: Optional[str] = None,
                      max_tokens: int = 150) -> VisionResult:
        return VisionResult(
            description="[Mock] 画面中有一个人，看起来正在看着镜头。",
            objects=["person", "face"],
            actions=["looking"],
            mood="neutral",
            confidence=0.7,
            tokens_used=50,
            cost_estimate=0.0,
            provider_used="mock",
            latency_ms=50,
        )

    async def health_check(self) -> bool:
        return True


class OpenAIVisionProvider(BaseVisionProvider):
    """OpenAI GPT-4o / GPT-4-vision 视觉分析"""

    def __init__(self, config: VisionProviderConfig):
        self.config = config
        self._client = None

    @property
    def name(self) -> str:
        return f"openai/{self.config.model}"

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                api_key = os.environ.get(self.config.api_key_env, "")
                base_url = self.config.api_base
                self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            except ImportError:
                logger.error("openai package not installed")
                return None
        return self._client

    async def analyze(self, image_base64: str, prompt: Optional[str] = None,
                      max_tokens: int = 150) -> VisionResult:
        client = self._get_client()
        if client is None:
            return VisionResult(
                error="OpenAI client not available",
                provider_used=self.name,
            )

        default_prompt = (
            "请简要描述画面中看到的内容。重点关注："
            "是否有人、人在做什么、情绪状态、画面中的物品。"
            "用中文回答，不超过 100 字。"
        )
        user_prompt = prompt or default_prompt

        try:
            start = time.time()
            response = await client.chat.completions.create(
                model=self.config.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}",
                                "detail": "low",
                            },
                        },
                    ],
                }],
                max_tokens=max_tokens,
            )
            elapsed = int((time.time() - start) * 1000)

            text = response.choices[0].message.content or ""
            usage = response.usage

            # 费用估算 (GPT-4o: $2.50/1M input, $10/1M output，粗略)
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0
            total_tokens = input_tokens + output_tokens
            cost = (input_tokens * 2.5 + output_tokens * 10) / 1_000_000

            return VisionResult(
                description=text,
                objects=self._extract_objects(text),
                confidence=0.8,
                tokens_used=total_tokens,
                cost_estimate=cost,
                provider_used=self.name,
                latency_ms=elapsed,
            )
        except Exception as e:
            logger.error("OpenAI vision error: %s", e)
            return VisionResult(
                error=str(e)[:200],
                provider_used=self.name,
            )

    def _extract_objects(self, text: str) -> List[str]:
        """从描述中简单提取物品"""
        items = []
        keywords = ["手机", "书本", "杯子", "电脑", "眼镜", "笔", "键盘",
                    "鼠标", "衣服", "食物", "饮料", "遥控器", "手表", "耳机"]
        for kw in keywords:
            if kw in text:
                items.append(kw)
        return items[:5]

    async def health_check(self) -> bool:
        try:
            client = self._get_client()
            if client is None:
                return False
            resp = await client.models.list()
            return len(resp.data) > 0
        except Exception:
            return False


class AnthropicVisionProvider(BaseVisionProvider):
    """Anthropic Claude 视觉分析"""

    def __init__(self, config: VisionProviderConfig):
        self.config = config
        self._client = None

    @property
    def name(self) -> str:
        return f"anthropic/{self.config.model}"

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                api_key = os.environ.get(self.config.api_key_env, "")
                self._client = anthropic.AsyncAnthropic(api_key=api_key)
            except ImportError:
                logger.error("anthropic package not installed")
                return None
        return self._client

    async def analyze(self, image_base64: str, prompt: Optional[str] = None,
                      max_tokens: int = 150) -> VisionResult:
        client = self._get_client()
        if client is None:
            return VisionResult(error="Anthropic client not available", provider_used=self.name)

        default_prompt = (
            "Briefly describe what you see in this image. Focus on: "
            "whether anyone is present, what they're doing, mood, and objects. "
            "Answer in Chinese, under 100 characters."
        )
        user_prompt = prompt or default_prompt

        try:
            start = time.time()
            response = await client.messages.create(
                model=self.config.model,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                    ],
                }],
            )
            elapsed = int((time.time() - start) * 1000)

            text = response.content[0].text if response.content else ""
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0
            # Claude 3.5 Sonnet: $3/1M input, $15/1M output
            cost = (input_tokens * 3 + output_tokens * 15) / 1_000_000

            return VisionResult(
                description=text,
                confidence=0.8,
                tokens_used=input_tokens + output_tokens,
                cost_estimate=cost,
                provider_used=self.name,
                latency_ms=elapsed,
            )
        except Exception as e:
            logger.error("Anthropic vision error: %s", e)
            return VisionResult(error=str(e)[:200], provider_used=self.name)

    async def health_check(self) -> bool:
        return self._get_client() is not None


# Provider 工厂
PROVIDER_REGISTRY = {
    "mock": MockVisionProvider,
    "openai": OpenAIVisionProvider,
    "anthropic": AnthropicVisionProvider,
}


class NoopVisionProvider(BaseVisionProvider):
    """空实现 —— 外部上传关闭时使用"""

    @property
    def name(self) -> str:
        return "noop"

    async def analyze(self, image_base64: str, prompt: Optional[str] = None,
                      max_tokens: int = 150) -> VisionResult:
        return VisionResult(description="External vision disabled", provider_used="noop")

    async def health_check(self) -> bool:
        return False


class VisionProviderManager:
    """视觉模型管理器"""

    def __init__(self, config: Optional[VisionProviderConfig] = None,
                 enabled: bool = False):
        self.config = config or VisionProviderConfig()
        self.enabled = enabled

        # 初始化 provider
        provider_cls = PROVIDER_REGISTRY.get(self.config.provider, MockVisionProvider)
        if issubclass(provider_cls, MockVisionProvider):
            self.provider: BaseVisionProvider = provider_cls()
        else:
            self.provider = provider_cls(self.config)

        self.rate_limiter = RateLimiter(
            max_frames_per_minute=self.config.max_frames_per_minute,
            max_cost_per_hour=self.config.max_cost_per_hour,
            max_cost_per_day=self.config.max_cost_per_day,
        )
        self._analyze_count: int = 0
        self._error_count: int = 0

    async def initialize(self):
        if not self.enabled:
            logger.info("External vision provider: DISABLED (default)")
            self.provider = NoopVisionProvider()
            return

        logger.info("External vision provider: %s (model=%s)",
                     self.config.provider, self.config.model)

    def set_enabled(self, enabled: bool):
        """切换外部上传开关"""
        was_enabled = self.enabled
        self.enabled = enabled
        if not enabled:
            self.provider = NoopVisionProvider()
            logger.info("External vision: DISABLED by user")
        elif not was_enabled:
            # 重新启用
            provider_cls = PROVIDER_REGISTRY.get(self.config.provider, MockVisionProvider)
            if issubclass(provider_cls, MockVisionProvider):
                self.provider = provider_cls()
            else:
                self.provider = provider_cls(self.config)
            logger.info("External vision: ENABLED by user")

    async def analyze_frame(self, image_base64: str,
                            prompt: Optional[str] = None,
                            max_tokens: int = 150) -> Optional[VisionResult]:
        """分析一帧，带频率/费用限制和降级策略"""
        if not self.enabled:
            return None

        allowed, reason = self.rate_limiter.can_send()
        if not allowed:
            logger.debug("Vision rate limit: %s", reason)
            if self.config.fallback_on_limit == "skip":
                return None
            elif self.config.fallback_on_limit == "local_only":
                return VisionResult(
                    description="[Rate limited, local only]",
                    provider_used="local",
                )
            return None

        self._analyze_count += 1
        try:
            result = await self.provider.analyze(image_base64, prompt, max_tokens)
            self.rate_limiter.record_send(result.cost_estimate)

            if result.error:
                self._error_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            logger.error("Vision analysis exception: %s", e)
            return VisionResult(error=str(e)[:200], provider_used=self.provider.name)

    def can_send(self) -> tuple:
        return self.rate_limiter.can_send()

    def get_usage_stats(self) -> Dict[str, Any]:
        stats = self.rate_limiter.get_stats()
        stats.update({
            "enabled": self.enabled,
            "provider": self.provider.name,
            "analyze_count": self._analyze_count,
            "error_count": self._error_count,
        })
        return stats

    def reset_counters(self):
        self._analyze_count = 0
        self._error_count = 0
