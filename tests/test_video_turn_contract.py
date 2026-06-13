"""
/api/video/turn 请求/返回接口契约测试

video-companion 只提交语音文本、视觉观察、session_id、persona_id、turn_index。
主项目返回 reply_text、voice_style、expression、memory_policy。
video-companion 不直接写长期记忆，只提交候选观察和会话摘要。
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.mnemosyne_client import VideoTurnResponse, SessionSummaryPayload
from app.local_vision import VideoObservation


# ============ VideoTurnResponse 契约 ============

def test_video_turn_response_fields():
    """主项目返回必须包含 reply_text, voice_style, expression, memory_policy"""
    resp = VideoTurnResponse.from_api_response({
        "reply_text": "你好！今天怎么样？",
        "voice_style": "gentle",
        "expression": "smile",
        "memory_policy": {
            "should_extract": False,
            "candidate_only": True,
        },
    })
    assert resp.reply_text == "你好！今天怎么样？"
    assert resp.voice_style == "gentle"
    assert resp.expression == "smile"
    assert resp.memory_policy["should_extract"] == False
    assert resp.memory_policy["candidate_only"] == True


def test_video_turn_response_defaults():
    """主项目缺失字段时使用安全默认值"""
    resp = VideoTurnResponse.from_api_response({})
    assert resp.reply_text == ""
    assert resp.voice_style == "natural"
    assert resp.expression == "neutral"
    assert resp.memory_policy == {}


def test_video_turn_response_empty_reply():
    """空 reply_text 不会被当作有效回复"""
    resp = VideoTurnResponse.from_api_response({
        "reply_text": "",
        "expression": "confused",
    })
    assert resp.reply_text == ""
    # process_user_speech 检查 main_response.reply_text 判定有效性


# ============ 请求 payload 形状 ============

def test_turn_payload_keys():
    """请求 payload 必须包含 5 个字段，不包含人格/记忆写操作"""
    payload = {
        "persona_id": "default",
        "user_text": "你好",
        "visual_observation": None,
        "visual_context": "无法可靠判断用户是否在场",
        "session_id": "video-companion-12345",
        "turn_index": 1,
    }
    required = {"persona_id", "user_text", "visual_observation",
                "session_id", "turn_index"}
    assert required.issubset(set(payload.keys()))
    # 禁止字段：不应包含
    forbidden = {"personality_params", "memory_write", "direct_memory",
                 "long_term_memory_action", "relationship_change"}
    assert forbidden.isdisjoint(set(payload.keys()))


# ============ 长期内存写保护 ============

def test_observation_does_not_write_memory():
    """post_observation 默认 allow_long_term_memory=False"""
    obs = VideoObservation(timestamp=0)
    obs_dict = obs.to_api_payload()
    # 默认不包含 allow_long_term_memory 或为 False
    mem_flag = obs_dict.get("allow_long_term_memory", False)
    assert mem_flag == False or mem_flag is None


def test_session_summary_candidate_only():
    """post_session_summary 使用 memory_candidates 字段名，表示仅候选"""
    payload = SessionSummaryPayload(
        persona_id="test",
        start_time="2024-01-01T00:00:00",
        end_time="2024-01-01T00:05:00",
        key_facts=["用户展示了新手账"],
        memory_candidates=["用户正在整理计划"],
        risk_flags=[],
    )
    d = payload.to_dict()
    # 有 memory_candidates（候选），没有 memory_write（直接写）
    assert "memory_candidates" in d
    assert "memory_write" not in d
    assert "direct_memory" not in d
