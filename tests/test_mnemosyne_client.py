"""
mnemosyne_client.py 测试套件

测试覆盖：
1. 客户端初始化
2. SessionContext 数据结构
3. SessionSummary 数据结构
4. 离线模式回退
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


def test_session_context_defaults():
    """测试8: SessionContext 默认值"""
    ctx = SessionContext()
    assert ctx.persona_id == ""
    assert ctx.speaking_style == "casual"
    assert ctx.relationship_status == "acquaintance"
    assert ctx.boundaries == []
    assert ctx.consent_state == {}
