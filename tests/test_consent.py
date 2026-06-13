"""
consent.py 测试套件

测试覆盖：
1. 授权默认关闭
2. 单项授权/撤销
3. 批量撤销
4. 审计日志
5. 状态序列化
6. 回退兼容
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.consent import ConsentManager, ConsentItem, ConsentState


def test_default_all_off():
    """测试1: 所有授权默认关闭"""
    cm = ConsentManager()
    assert cm.can_capture_camera() == False
    assert cm.can_capture_microphone() == False
    assert cm.can_upload_to_vision_model() == False
    assert cm.can_save_summary() == False
    assert cm.can_save_observation() == False
    assert cm.is_privacy_safe() == True


def test_single_grant_revoke():
    """测试2: 单项授权和撤销"""
    cm = ConsentManager()
    cm.grant_camera(reason="test")
    assert cm.can_capture_camera() == True
    assert cm.is_privacy_safe() == False

    cm.revoke_camera(reason="test")
    assert cm.can_capture_camera() == False
    assert cm.is_privacy_safe() == True


def test_media_batch():
    """测试3: 媒体批量操作"""
    cm = ConsentManager()
    cm.grant_camera()
    cm.grant_microphone()
    assert cm.state.is_any_media_active() == True

    cm.revoke_all_media()
    assert cm.can_capture_camera() == False
    assert cm.can_capture_microphone() == False


def test_audit_log():
    """测试4: 审计日志记录"""
    cm = ConsentManager(enable_audit=True)
    cm.grant_camera(reason="user_request")
    cm.grant_microphone(reason="user_request")
    cm.revoke_camera(reason="privacy_concern")

    log = cm.get_audit_log()
    assert len(log) == 3
    assert log[0]["item"] == "camera"
    assert log[0]["new_value"] == True
    assert log[2]["item"] == "camera"
    assert log[2]["new_value"] == False


def test_state_serialization():
    """测试5: 状态序列化"""
    cm = ConsentManager()
    cm.grant_camera()
    cm.grant_external_vision()

    d = cm.to_dict()
    assert d["camera"] == True
    assert d["external_vision"] == True
    assert d["microphone"] == False

    # API payload
    api = cm.state.to_api_payload()
    assert api["camera"] == True
    assert api["external_vision_upload"] == True
    assert api["microphone"] == False


def test_revoke_all():
    """测试6: 全部撤销"""
    cm = ConsentManager()
    cm.grant_camera()
    cm.grant_microphone()
    cm.grant_external_vision()
    cm.grant_external_vision()  # 重复调用
    cm.state.grant(ConsentItem.SAVE_SUMMARY)
    cm.state.grant(ConsentItem.SAVE_OBSERVATION)

    cm.revoke_all(reason="session_end")
    assert cm.is_privacy_safe() == True
    assert cm.can_capture_camera() == False
    assert cm.can_capture_microphone() == False


def test_from_dict():
    """测试7: 从 dict 恢复状态"""
    data = {"camera": True, "microphone": False, "external_vision": True}
    state = ConsentState.from_dict(data)
    assert state.camera == True
    assert state.external_vision == True
    assert state.microphone == False
    assert state.save_summary == False  # 缺失用默认值


def test_consent_item_enum():
    """测试8: ConsentItem 枚举操作"""
    assert len(ConsentItem.all_items()) == 5
    assert ConsentItem.CAMERA in ConsentItem.media_items()
    assert ConsentItem.EXTERNAL_VISION in ConsentItem.upload_items()
    assert ConsentItem("camera") == ConsentItem.CAMERA
