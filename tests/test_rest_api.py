"""
FastAPI REST 授权接口集成测试

验证 /api/consent/{item}/grant 和 /api/consent/{item}/revoke
对所有 consent item 的正确行为，特别确认 external_vision 不会 await 同步函数。
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(level=logging.WARNING)

from fastapi.testclient import TestClient
from app.server import VideoCompanionServer, create_app


def _make_client():
    server = VideoCompanionServer()
    app = create_app(server)
    return TestClient(app), server


# ============ external_vision ============

def test_rest_external_vision_grant():
    """external_vision grant: 不 await 同步函数，vision.enabled 变为 True"""
    client, server = _make_client()
    resp = client.post("/api/consent/external_vision/grant")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "granted"
    assert data["item"] == "external_vision"
    assert server.vision.enabled == True
    assert server.consent.can_upload_to_vision_model() == True


def test_rest_external_vision_revoke():
    """external_vision revoke: 不 await 同步函数，vision.enabled 变为 False"""
    client, server = _make_client()
    # 先 grant
    client.post("/api/consent/external_vision/grant")
    assert server.vision.enabled == True

    resp = client.post("/api/consent/external_vision/revoke")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "revoked"
    assert data["item"] == "external_vision"
    assert server.vision.enabled == False
    assert server.consent.can_upload_to_vision_model() == False


def test_rest_external_vision_grant_revoke_cycle():
    """external_vision grant → revoke → grant 完整周期"""
    client, server = _make_client()

    # 初始状态
    assert server.vision.enabled == False

    # grant
    r1 = client.post("/api/consent/external_vision/grant")
    assert r1.status_code == 200
    assert server.vision.enabled == True

    # revoke
    r2 = client.post("/api/consent/external_vision/revoke")
    assert r2.status_code == 200
    assert server.vision.enabled == False

    # 再次 grant
    r3 = client.post("/api/consent/external_vision/grant")
    assert r3.status_code == 200
    assert server.vision.enabled == True

    # 审计日志应有 3 条记录
    log = server.consent.get_audit_log()
    assert len(log) >= 3


# ============ camera ============

def test_rest_camera_grant():
    """camera grant: 启动摄像头"""
    client, server = _make_client()
    resp = client.post("/api/consent/camera/grant")
    assert resp.status_code == 200
    assert server.consent.can_capture_camera() == True
    assert server.camera.is_active() == True


def test_rest_camera_revoke():
    """camera revoke: 停止摄像头"""
    client, server = _make_client()
    client.post("/api/consent/camera/grant")
    resp = client.post("/api/consent/camera/revoke")
    assert resp.status_code == 200
    assert server.consent.can_capture_camera() == False
    assert not server.camera.is_active()


# ============ microphone ============

def test_rest_microphone_grant():
    """microphone grant: 启动监听"""
    client, server = _make_client()
    resp = client.post("/api/consent/microphone/grant")
    assert resp.status_code == 200
    assert server.consent.can_capture_microphone() == True
    assert server.audio.is_listening() == True


def test_rest_microphone_revoke():
    """microphone revoke: 停止监听"""
    client, server = _make_client()
    client.post("/api/consent/microphone/grant")
    resp = client.post("/api/consent/microphone/revoke")
    assert resp.status_code == 200
    assert server.consent.can_capture_microphone() == False
    assert not server.audio.is_listening()


# ============ 未知 item ============

def test_rest_unknown_item():
    """未知 consent item 返回 400"""
    client, server = _make_client()
    resp = client.post("/api/consent/unknown_item/grant")
    assert resp.status_code == 400


# ============ 只读 ============

def test_rest_get_consent():
    """GET /api/consent 只读"""
    client, server = _make_client()
    resp = client.get("/api/consent")
    assert resp.status_code == 200
    data = resp.json()
    assert "camera" in data
    assert "microphone" in data
    assert "external_vision" in data
    # 默认全关
    assert data["camera"] == False
    assert data["external_vision"] == False


# ============ revoke-all ============

def test_rest_revoke_all():
    """revoke-all 全关"""
    client, server = _make_client()
    client.post("/api/consent/camera/grant")
    client.post("/api/consent/microphone/grant")
    client.post("/api/consent/external_vision/grant")

    resp = client.post("/api/consent/revoke-all")
    assert resp.status_code == 200
    assert server.consent.is_privacy_safe() == True
    assert not server.camera.is_active()
    assert not server.audio.is_listening()
    assert server.vision.enabled == False
