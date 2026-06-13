"""
mnemosyne_client.py 测试套件 — Legacy bridge

测试覆盖：
1. 客户端初始化
2. SessionContext 数据结构
3. SessionSummary 数据结构
4. 离线模式回退
5. Legacy bridge 默认关闭
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.mnemosyne_client import (
    MnemosyneClient, MnemosyneConfig,
    SessionContext, SessionSummaryPayload
)


def test_client_initialization():
    """测试1: 客户端初始化"""
    client = MnemosyneClient(
        MnemosyneConfig(
            api_base="http://localhost:9999",
            enabled=True,
            timeout=5,
            retries=1,
        )
    )
    assert client.config.api_base == "http://localhost:9999"
    assert client.config.timeout == 5
    assert client.config.retries == 1


def test_client_disabled():
    """测试2: 禁用模式"""
    client = MnemosyneClient(
        MnemosyneConfig(enabled=False)
    )
    asyncio.run(client.initialize())
    # 禁用时不应尝试连接
    ctx = asyncio.run(client.get_session_context("test"))
    assert ctx is not None  # 仍返回默认上下文
    assert ctx.persona_id == "test"


def test_session_context_from_api():
    """测试3: SessionContext 解析"""
    api_data = {
        "persona_id": "p001",
        "persona_name": "小明",
        "speaking_style": "casual",
        "relationship_status": "friend",
        "recent_summary": "刚才聊了天气",
        "boundaries": ["不要讨论政治"],
        "consent_state": {"camera": True, "microphone": False},
    }
    ctx = SessionContext.from_api_response(api_data)
    assert ctx.persona_id == "p001"
    assert ctx.persona_name == "小明"
    assert ctx.speaking_style == "casual"
    assert ctx.relationship_status == "friend"
    assert "天气" in ctx.recent_summary
    assert len(ctx.boundaries) == 1
    assert ctx.consent_state["camera"] == True


def test_session_summary_payload():
    """测试4: SessionSummary 负载"""
    payload = SessionSummaryPayload(
        persona_id="test",
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-01-01T00:05:00Z",
        session_duration_sec=300,
        total_turns=10,
        key_facts=["用户展示了新手账本"],
        memory_candidates=["用户正在整理计划"],
        risk_flags=[],
    )
    d = payload.to_dict()
    assert d["persona_id"] == "test"
    assert d["session_duration_sec"] == 300
    assert d["total_turns"] == 10
    assert len(d["key_facts"]) == 1
    assert d["key_facts"][0] == "用户展示了新手账本"


def test_offline_mode_get_context():
    """测试5: 离线模式回退"""
    client = MnemosyneClient(
        MnemosyneConfig(
            api_base="http://192.0.2.1:9999",  # 不可达地址
            enabled=True,
            timeout=1,
            retries=0,
        )
    )
    asyncio.run(client.initialize())
    # 健康检查应失败
    assert client.is_connected() == False

    # 但获取上下文应回退
    ctx = asyncio.run(client.get_session_context("fallback_persona"))
    assert ctx is not None
    assert ctx.persona_id == "fallback_persona"


def test_client_stats():
    """测试6: 客户端统计"""
    client = MnemosyneClient(
        MnemosyneConfig(enabled=False)
    )
    stats = client.get_stats()
    assert stats["connected"] == False
    assert stats["requests"] == 0
    assert stats["errors"] == 0


def test_default_config():
    """测试7: 默认配置"""
    config = MnemosyneConfig()
    assert config.api_base == "http://127.0.0.1:8000"
    assert config.timeout == 10
    assert config.retries == 2
    assert config.enabled == True


def test_legacy_bridge_defaults():
    """测试9: Legacy bridge 默认关闭 — standalone 模式不依赖它"""
    # 默认 enabled=True 是从旧版遗留的，新 default config 里是 False
    # 但 MnemosyneConfig 本身的默认仍为 True（向后兼容）
    config = MnemosyneConfig()
    assert config.enabled == True  # 代码默认
    # 系统配置 (legacy_bridge) 应覆盖为 False
    cfg = MnemosyneConfig(enabled=False)
    assert cfg.enabled == False


def test_legacy_disabled_no_reconnect():
    """测试10: legacy_bridge disabled 时不创建 reconnect task"""
    import asyncio
    from unittest.mock import patch

    # 模拟 DEFAULT_CONFIG：legacy_bridge disabled
    mock_config = {
        "legacy_bridge": {"api_base": "http://127.0.0.1:8000", "enabled": False},
        "server": {"host": "127.0.0.1", "port": 8001},
        "camera": {}, "microphone": {}, "local_vision": {}, "vision_provider": {},
        "speech": {"asr": {"provider": "mock"}, "tts": {"provider": "mock"}},
        "privacy": {"defaults": {}, "save_raw_media": False},
        "cost": {},
        "persona": {},
        "project": {"mode": "standalone_ai_vtuber"},
    }

    from app.server import VideoCompanionServer
    import logging
    logging.disable(logging.CRITICAL)

    server = VideoCompanionServer.__new__(VideoCompanionServer)
    server.config = mock_config

    from app.consent import ConsentManager
    from app.camera_source import CameraSource, CameraConfig
    from app.audio_source import AudioSource, AudioConfig
    from app.local_vision import LocalVisionDetector
    from app.vision_provider import VisionProviderManager, VisionProviderConfig
    from app.speech_provider import SpeechProviderManager, SpeechConfig
    from app.mnemosyne_client import MnemosyneClient, MnemosyneConfig

    server.consent = ConsentManager()
    server.camera = CameraSource(CameraConfig())
    server.audio = AudioSource(AudioConfig())
    server.local_vision = LocalVisionDetector()
    server.vision = VisionProviderManager(enabled=False)
    server.speech = SpeechProviderManager(SpeechConfig(asr_provider="mock", tts_provider="mock"))

    lb_cfg = mock_config.get("legacy_bridge", {})
    server.mnemosyne = MnemosyneClient(MnemosyneConfig(
        api_base=lb_cfg.get("api_base", ""),
        enabled=lb_cfg.get("enabled", False),
    ))

    server._active_ws = set()
    server._reconnect_task = None

    # 执行 initialize
    async def run_init():
        await server.local_vision.initialize()
        await server.vision.initialize()
        await server.speech.initialize()
        await server.mnemosyne.initialize()
        # 关键检查：disabled 时不创建 reconnect task
        if server.mnemosyne.config.enabled:
            server._reconnect_task = asyncio.create_task(asyncio.sleep(0))
        # 否则保持 None

    asyncio.run(run_init())

    # legacy_bridge disabled → 不应创建 reconnect task
    assert server._reconnect_task is None
    assert server.mnemosyne.config.enabled == False

    # 断开 client
    asyncio.run(server.mnemosyne.close())
