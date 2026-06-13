"""
local_vision.py 测试套件

测试覆盖：
1. 初始化
2. 空帧/无效帧检测
3. VideoObservation 数据结构
4. 回退模式 (无 OpenCV)
"""

import sys, os, time, base64, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.local_vision import (
    LocalVisionDetector, VideoObservation, FaceDetection,
    MotionDetection, MoodLabel, MotionLabel, BodyDetection
)


async def _init(detector):
    await detector.initialize()


def test_initialization():
    """测试1: 初始化检测器"""
    detector = LocalVisionDetector()
    asyncio.run(_init(detector))
    # 应成功初始化（至少回退模式）
    assert detector._initialized == True


def test_empty_frame():
    """测试2: 空帧检测"""
    detector = LocalVisionDetector()
    asyncio.run(_init(detector))

    obs = asyncio.run(detector.detect(
        data_base64="", width=640, height=480,
        timestamp=time.time()
    ))
    assert obs.camera_usable == False
    assert obs.user_present is None
    assert obs.presence_status == "unknown"


def test_fallback_mode():
    """测试3: 无 OpenCV 回退模式"""
    detector = LocalVisionDetector()
    asyncio.run(_init(detector))

    obs = asyncio.run(detector.detect(
        data_base64="test", width=640, height=480,
        timestamp=time.time()
    ))

    if not sys.modules.get('cv2'):
        # 无 OpenCV：状态应为 unknown
        assert obs.user_present is None
        assert obs.presence_status == "unknown"
        assert obs.detector_available == False
    else:
        # 有 OpenCV：假数据可能检测不到人脸 → absent 或 unknown
        assert obs.user_present is not True or obs.presence_status != "unknown"


def test_video_observation_to_dict():
    """测试4: VideoObservation 序列化"""
    obs = VideoObservation(
        timestamp=time.time(),
        user_present=True,
        presence_status="present",
        presence_confidence=0.9,
        detector_available=True,
        camera_usable=True,
        face=FaceDetection(present=True, count=1, rough_mood=MoodLabel.NEUTRAL),
        motion=MotionDetection(level=MotionLabel.SLIGHT, motion_score=0.15),
        object_hint="book",
    )
    d = obs.to_dict()
    assert d["user_present"] == True
    assert d["presence_status"] == "present"
    assert d["presence_confidence"] == 0.9
    assert d["detector_available"] == True
    assert d["face"]["present"] == True
    assert d["face"]["rough_mood"] == "neutral"
    assert d["motion"]["level"] == "slight"
    assert d["object_hint"] == "book"


def test_video_observation_summary():
    """测试5: VideoObservation 摘要"""
    obs = VideoObservation(
        timestamp=time.time(),
        user_present=True,
        presence_status="present",
        face=FaceDetection(present=True, rough_mood=MoodLabel.FOCUSED),
        motion=MotionDetection(level=MotionLabel.MODERATE),
        object_hint="laptop",
    )
    s = obs.summary()
    assert "检测到用户" in s
    assert "情绪" in s
    assert "动作" in s
    assert "laptop" in s


def test_api_payload():
    """测试6: API 负载格式"""
    obs = VideoObservation(
        timestamp=1234567890.0,
        user_present=True,
        presence_status="present",
        external_analysis=True,
        external_description="A person looking at camera",
    )
    payload = obs.to_api_payload()
    assert payload["timestamp"] == 1234567890.0
    assert payload["user_present"] == True
    assert payload["presence_status"] == "present"
    assert payload["external_analysis"] == True
    assert payload["external_description"] == "A person looking at camera"
    assert "face" in payload
    assert "body" in payload
    assert "motion" in payload


def test_count_increment():
    """测试7: 检测计数递增"""
    detector = LocalVisionDetector()
    asyncio.run(_init(detector))

    for i in range(3):
        asyncio.run(detector.detect(
            data_base64="test", width=640, height=480,
            timestamp=time.time()
        ))
    assert detector.get_detection_count() == 3


def test_mood_labels():
    """测试8: 情绪标签枚举"""
    assert MoodLabel.NEUTRAL.value == "neutral"
    assert MoodLabel.HAPPY.value == "happy"
    assert MoodLabel.FOCUSED.value == "focused"
    assert len(list(MoodLabel)) >= 6
