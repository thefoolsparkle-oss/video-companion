"""
本地视觉检测模块 (V2 完善版)

基于 OpenCV/MediaPipe 做本地人脸检测、人体关键点、动作检测。
不依赖外部模型，作为视觉模型前置过滤。
支持：
- 人脸检测（OpenCV Haar Cascade / MediaPipe）
- 动作检测（帧差法）
- 亮度/模糊度检测
- 纯 Python 回退（无 OpenCV 时）
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
import time
import base64
import logging
import os

logger = logging.getLogger(__name__)

# 尝试导入 OpenCV
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    logger.info("OpenCV not available, using pure-Python fallback")


class MoodLabel(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    SURPRISED = "surprised"
    FOCUSED = "focused"
    CONFUSED = "confused"
    UNKNOWN = "unknown"


class MotionLabel(str, Enum):
    STILL = "still"
    SLIGHT = "slight"
    MODERATE = "moderate"
    ACTIVE = "active"


@dataclass
class FaceDetection:
    """人脸检测结果"""
    present: bool = False
    count: int = 0
    bbox: Optional[List[int]] = None
    confidence: float = 0.0
    rough_mood: MoodLabel = MoodLabel.UNKNOWN

    def to_dict(self) -> dict:
        return {
            "present": self.present,
            "count": self.count,
            "confidence": self.confidence,
            "rough_mood": self.rough_mood.value,
        }


@dataclass
class BodyDetection:
    """人体检测结果"""
    present: bool = False
    count: int = 0
    pose_landmarks: Optional[List[Dict[str, float]]] = None

    def to_dict(self) -> dict:
        return {"present": self.present, "count": self.count}


@dataclass
class MotionDetection:
    """动作检测结果"""
    level: MotionLabel = MotionLabel.STILL
    motion_score: float = 0.0
    changed_regions: int = 0

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "score": round(self.motion_score, 4),
            "changed_regions": self.changed_regions,
        }


@dataclass
class VideoObservation:
    """视频画面结构化观察"""
    timestamp: float
    # user_present: True=检测到人脸, False=明确无人, None=未知
    user_present: Optional[bool] = None
    presence_status: str = "unknown"    # present | absent | unknown | unusable
    presence_confidence: float = 0.0
    detector_available: bool = False
    camera_usable: bool = True
    face: FaceDetection = field(default_factory=FaceDetection)
    body: BodyDetection = field(default_factory=BodyDetection)
    motion: MotionDetection = field(default_factory=MotionDetection)
    object_hint: Optional[str] = None
    external_analysis: bool = False
    external_description: Optional[str] = None
    brightness: float = 0.0
    blur_score: float = 0.0
    is_usable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "user_present": self.user_present,
            "presence_status": self.presence_status,
            "presence_confidence": self.presence_confidence,
            "detector_available": self.detector_available,
            "camera_usable": self.camera_usable,
            "face": self.face.to_dict(),
            "body": self.body.to_dict(),
            "motion": self.motion.to_dict(),
            "object_hint": self.object_hint,
            "brightness": round(self.brightness, 2),
            "blur_score": round(self.blur_score, 2),
            "is_usable": self.is_usable,
            "external_analysis": self.external_analysis,
            "external_description": self.external_description,
        }

    def to_api_payload(self) -> dict:
        return self.to_dict()

    def summary(self) -> str:
        parts = []
        if self.presence_status == "present":
            parts.append("检测到用户")
            if self.face.rough_mood != MoodLabel.UNKNOWN:
                parts.append(f"情绪: {self.face.rough_mood.value}")
        elif self.presence_status == "absent":
            parts.append("未检测到用户")
        elif self.presence_status == "unusable":
            parts.append("画面不可用")
        else:
            parts.append("用户在场状态未知")
        if self.motion.level != MotionLabel.STILL:
            parts.append(f"动作: {self.motion.level.value}")
        if self.object_hint:
            parts.append(f"物品: {self.object_hint}")
        if not self.is_usable:
            parts.append("画面质量不佳")
        return ", ".join(parts) if parts else "画面正常"


class LocalVisionDetector:
    """本地视觉检测器"""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._face_detector = None
        self._face_cascade_path = None
        self._prev_frame_gray = None
        self._initialized = False
        self._detection_count: int = 0

    async def initialize(self):
        """初始化检测模型"""
        enabled = self.config.get("enabled_detectors", ["face", "motion"])
        face_confidence = self.config.get("face_confidence", 0.5)

        if "face" in enabled:
            if HAS_OPENCV:
                self._init_opencv_face_detector()
            else:
                logger.info("Face detection: using fallback (always present=True for testing)")
            logger.info("Face detector ready (confidence=%.2f)", face_confidence)

        self._initialized = True
        logger.info(
            "Local vision initialized (detectors=%s, opencv=%s)",
            enabled, HAS_OPENCV
        )

    def _init_opencv_face_detector(self):
        """初始化 OpenCV 人脸检测器"""
        cascade_paths = [
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_default.xml",
        ]
        for path in cascade_paths:
            if os.path.exists(path):
                self._face_cascade_path = path
                self._face_detector = cv2.CascadeClassifier(path)
                if not self._face_detector.empty():
                    logger.info("OpenCV face cascade loaded: %s", path)
                    return
        logger.warning("OpenCV face cascade not found, face detection disabled")

    def _decode_base64_to_np(self, data_base64: str) -> Optional[Any]:
        """将 base64 解码为 numpy 数组"""
        if not data_base64 or not HAS_OPENCV:
            return None
        try:
            img_bytes = base64.b64decode(data_base64)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            logger.debug("Frame decode error: %s", e)
            return None

    async def detect(self, data_base64: str, width: int, height: int,
                     timestamp: float) -> VideoObservation:
        """对一帧执行本地检测"""
        self._detection_count += 1
        observation = VideoObservation(
            timestamp=timestamp,
            camera_usable=True,
            user_present=None,
            presence_status="unknown",
            presence_confidence=0.0,
            detector_available=False,
        )

        if not data_base64:
            observation.camera_usable = False
            observation.presence_status = "unknown"
            return observation

        if not HAS_OPENCV:
            observation.presence_status = "unknown"
            observation.detector_available = False
            return observation

        img = self._decode_base64_to_np(data_base64)
        if img is None:
            observation.camera_usable = False
            observation.presence_status = "unknown"
            return observation

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 画质评估（先做——太暗或太模糊直接判定不可用）
        observation.brightness = self._calculate_brightness(gray)
        observation.blur_score = self._calculate_blur(gray)
        observation.is_usable = self._assess_usability(observation)

        if not observation.is_usable:
            observation.presence_status = "unusable"
            observation.camera_usable = True  # 摄像头是开的但画面不可用
            self._prev_frame_gray = gray
            return observation

        # 检查人脸检测器是否可用
        detector_ok = (self._face_detector is not None and
                       not self._face_detector.empty())
        observation.detector_available = detector_ok

        if detector_ok:
            # 真实人脸检测
            face = self._detect_face_opencv(gray)
            observation.face = face
            observation.face.confidence = face.confidence
            if face.present:
                observation.user_present = True
                observation.presence_status = "present"
                observation.presence_confidence = face.confidence
            else:
                observation.user_present = False
                observation.presence_status = "absent"
                observation.presence_confidence = face.confidence
        else:
            # 检测器不可用 → 未知
            observation.user_present = None
            observation.presence_status = "unknown"
            observation.presence_confidence = 0.0

        # 动作检测
        motion = self._detect_motion_opencv(gray)
        observation.motion = motion

        self._prev_frame_gray = gray
        return observation

    def _detect_face_opencv(self, gray) -> FaceDetection:
        """OpenCV 人脸检测"""
        if self._face_detector is None or self._face_detector.empty():
            return FaceDetection(present=False, count=0, confidence=0.0)
        try:
            faces = self._face_detector.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5,
                minSize=(30, 30), flags=cv2.CASCADE_SCALE_IMAGE
            )
            if len(faces) > 0:
                x, y, w, h = faces[0]
                return FaceDetection(
                    present=True,
                    count=len(faces),
                    bbox=[int(x), int(y), int(w), int(h)],
                    confidence=0.8,
                )
            return FaceDetection(present=False, count=0, confidence=0.3)
        except Exception as e:
            logger.warning("Face detection error: %s", e)
            return FaceDetection(present=False, count=0, confidence=0.0)

    def _detect_motion_opencv(self, gray) -> MotionDetection:
        """基于帧差的动作检测"""
        if self._prev_frame_gray is None or gray.shape != self._prev_frame_gray.shape:
            return MotionDetection()

        try:
            diff = cv2.absdiff(gray, self._prev_frame_gray)
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            motion_pixels = cv2.countNonZero(thresh)
            total_pixels = gray.shape[0] * gray.shape[1]
            motion_ratio = motion_pixels / total_pixels if total_pixels > 0 else 0

            sensitivity = self.config.get("motion_sensitivity", 0.3)
            if motion_ratio < sensitivity * 0.3:
                level = MotionLabel.STILL
            elif motion_ratio < sensitivity:
                level = MotionLabel.SLIGHT
            elif motion_ratio < sensitivity * 2:
                level = MotionLabel.MODERATE
            else:
                level = MotionLabel.ACTIVE

            # 计算变化区域数
            contours, _ = cv2.findContours(
                thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            changed_regions = len(contours)

            return MotionDetection(
                level=level,
                motion_score=motion_ratio,
                changed_regions=changed_regions,
            )
        except Exception as e:
            logger.debug("Motion detection error: %s", e)
            return MotionDetection()

    def _calculate_brightness(self, gray) -> float:
        """计算画面平均亮度 (0-1)"""
        try:
            return float(np.mean(gray)) / 255.0
        except Exception:
            return 0.5

    def _calculate_blur(self, gray) -> float:
        """计算画面模糊度（Laplacian 方差，越高越清晰）"""
        try:
            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            return float(laplacian.var())
        except Exception:
            return 100.0

    def _assess_usability(self, obs: VideoObservation) -> bool:
        """综合评估画面是否可用"""
        if obs.brightness < 0.05:
            return False
        if obs.blur_score < 10:
            return False
        return True

    def get_detection_count(self) -> int:
        return self._detection_count
