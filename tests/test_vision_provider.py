"""
vision_provider.py 测试套件

测试覆盖：
1. Mock provider
2. Rate limiter
3. Provider manager
4. 启用/禁用切换
"""

import sys, os, time, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.vision_provider import (
    VisionProviderManager, VisionProviderConfig,
    MockVisionProvider, NoopVisionProvider, RateLimiter,
    VisionResult
)


def test_mock_provider():
    """测试1: Mock provider 分析"""
    provider = MockVisionProvider()

    result = asyncio.run(provider.analyze("fake_image_base64"))
    assert result.description != ""
    assert "Mock" in result.description
    assert result.provider_used == "mock"
    assert result.confidence > 0
    assert result.error is None


def test_mock_health_check():
    """测试2: Mock provider 健康检查"""
    provider = MockVisionProvider()
    assert asyncio.run(provider.health_check()) == True


def test_rate_limiter_can_send():
    """测试3: 频率限制器 - 允许发送"""
    rl = RateLimiter(max_frames_per_minute=5, max_cost_per_hour=1.0)
    allowed, reason = rl.can_send()
    assert allowed == True
    assert reason == "ok"


def test_rate_limiter_limit():
    """测试4: 频率限制器 - 达到上限"""
    rl = RateLimiter(max_frames_per_minute=3, max_cost_per_hour=100)

    # 发送 3 帧
    for _ in range(3):
        rl.record_send(cost=0.01)

    allowed, reason = rl.can_send()
    assert allowed == False
    assert reason == "minute_limit"


def test_rate_limiter_cost():
    """测试5: 频率限制器 - 费用上限"""
    rl = RateLimiter(max_frames_per_minute=100, max_cost_per_hour=0.03)

    rl.record_send(cost=0.02)
    allowed, reason = rl.can_send()
    assert allowed == (0.02 < 0.03)

    rl.record_send(cost=0.02)
    allowed, reason = rl.can_send()
    if 0.04 >= 0.03:
        assert reason == "hourly_cost_limit"


def test_provider_manager_disabled():
    """测试6: Provider Manager 禁用状态"""
    mgr = VisionProviderManager(enabled=False)
    asyncio.run(mgr.initialize())

    # 禁用时不分析
    result = asyncio.run(mgr.analyze_frame("test_image"))
    assert result is None

    stats = mgr.get_usage_stats()
    assert stats["enabled"] == False


def test_provider_manager_enabled_mock():
    """测试7: Provider Manager 启用 (mock)"""
    mgr = VisionProviderManager(
        config=VisionProviderConfig(provider="mock"),
        enabled=True,
    )
    asyncio.run(mgr.initialize())

    result = asyncio.run(mgr.analyze_frame("test_image"))
    assert result is not None
    assert result.description != ""
    assert result.error is None

    stats = mgr.get_usage_stats()
    assert stats["enabled"] == True
    assert stats["analyze_count"] == 1


def test_enable_disable_toggle():
    """测试8: 启用/禁用切换"""
    mgr = VisionProviderManager(
        config=VisionProviderConfig(provider="mock"),
        enabled=False,
    )
    asyncio.run(mgr.initialize())

    # 禁用 -> 启用
    mgr.set_enabled(True)
    assert mgr.enabled == True

    result = asyncio.run(mgr.analyze_frame("test"))
    assert result is not None

    # 启用 -> 禁用
    mgr.set_enabled(False)
    assert mgr.enabled == False

    result2 = asyncio.run(mgr.analyze_frame("test"))
    assert result2 is None


def test_vision_result_to_dict():
    """测试9: VisionResult 序列化"""
    result = VisionResult(
        description="A person sitting at a desk",
        objects=["person", "desk"],
        actions=["sitting"],
        mood="focused",
        confidence=0.85,
        tokens_used=120,
        cost_estimate=0.0005,
        provider_used="mock",
        latency_ms=300,
    )
    d = result.to_dict()
    assert d["description"] == "A person sitting at a desk"
    assert d["objects"] == ["person", "desk"]
    assert d["confidence"] == 0.85
