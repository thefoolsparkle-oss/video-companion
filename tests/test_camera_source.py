"""
camera_source.py 测试套件

测试覆盖：
1. 初始化状态
2. 帧接收
3. 帧缓冲
4. 指标统计
5. 状态切换
6. 帧丢弃
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.camera_source import CameraSource, CameraConfig, CameraState, CameraFrame


def test_initial_state():
    """测试1: 初始状态为 OFF"""
    cam = CameraSource()
    assert cam.get_state() == CameraState.OFF
    assert cam.is_active() == False
    assert cam.get_latest_frame() is None


async def _start(cam):
    await cam.start()


def test_start_stop():
    """测试2: 启动和停止"""
    import asyncio
    cam = CameraSource()
    asyncio.run(_start(cam))
    assert cam.is_active() == True
    assert cam.get_state() == CameraState.ACTIVE

    asyncio.run(cam.stop())
    assert cam.is_active() == False
    assert cam.get_state() == CameraState.OFF


def test_receive_frame():
    """测试3: 接收帧"""
    import asyncio
    cam = CameraSource()
    asyncio.run(_start(cam))

    frame = cam.receive_frame(data_base64="test_base64_data", width=640, height=480)
    assert frame is not None
    assert frame.frame_id == 1
    assert frame.width == 640
    assert frame.height == 480
    assert frame.size_bytes > 0


def test_frame_buffer():
    """测试4: 帧缓冲管理"""
    import asyncio
    cam = CameraSource(CameraConfig(max_frame_buffer=3))
    asyncio.run(_start(cam))

    for i in range(5):
        cam.receive_frame(data_base64=f"frame_{i}", width=640, height=480)

    latest = cam.get_latest_frame()
    assert latest is not None
    assert latest.frame_id == 5

    # 缓冲区只保留最后 3 帧
    buffer = cam.get_frame_buffer_snapshot()
    assert len(buffer) == 3
    assert buffer[-1].frame_id == 5
    assert buffer[0].frame_id == 3


def test_frame_drop_when_off():
    """测试5: 关闭状态下丢弃帧"""
    cam = CameraSource()
    frame = cam.receive_frame(data_base64="test")
    assert frame is None
    assert cam.metrics.frames_dropped == 1


def test_metrics():
    """测试6: 指标统计"""
    import asyncio
    cam = CameraSource()
    asyncio.run(_start(cam))

    for i in range(10):
        cam.receive_frame(data_base64=f"f{i}", width=640, height=480)

    metrics = cam.get_metrics()
    assert metrics["frames_received"] == 10
    assert metrics["frames_dropped"] == 0
    assert metrics["avg_fps"] > 0


def test_error_handling():
    """测试7: 错误处理"""
    cam = CameraSource()
    cam.set_error("Test camera error")
    assert cam.get_state() == CameraState.ERROR
    assert cam.metrics.errors == 1


def test_recent_frames():
    """测试8: 获取最近帧"""
    import asyncio
    cam = CameraSource()
    asyncio.run(_start(cam))

    for i in range(5):
        cam.receive_frame(data_base64=f"f{i}", width=640, height=480)

    recent = cam.get_recent_frames(3)
    assert len(recent) == 3
    assert recent[-1].frame_id == 5
