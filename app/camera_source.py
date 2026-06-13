"""
摄像头采集抽象模块 (V2 完善版)

封装摄像头状态管理、帧缓冲、采集指标。
前端通过 getUserMedia 采集并通过 WebSocket 发送帧；
后端通过本模块管理状态和帧处理管线。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Deque
from collections import deque
import time
import logging

logger = logging.getLogger(__name__)


class CameraState(str, Enum):
    OFF = "off"
    STARTING = "starting"
    ACTIVE = "active"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


@dataclass
class CameraConfig:
    width: int = 640
    height: int = 480
    fps: int = 15
    capture_interval_sec: float = 2.0
    default_on: bool = False
    max_frame_buffer: int = 10


@dataclass
class CameraFrame:
    """从摄像头采集的一帧"""
    frame_id: int = 0
    timestamp: float = 0.0
    width: int = 640
    height: int = 480
    data: Optional[bytes] = None
    data_base64: Optional[str] = None
    format: str = "jpeg"
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "size_bytes": self.size_bytes,
        }


@dataclass
class CameraMetrics:
    """摄像头采集指标"""
    frames_received: int = 0
    frames_dropped: int = 0
    frames_processed: int = 0
    last_frame_time: float = 0.0
    avg_fps: float = 0.0
    errors: int = 0
    start_time: float = 0.0

    @property
    def uptime_sec(self) -> float:
        if self.start_time == 0:
            return 0.0
        return time.time() - self.start_time


class CameraSource:
    """摄像头采集源"""

    def __init__(self, config: Optional[CameraConfig] = None):
        self.config = config or CameraConfig()
        self.state = CameraState.OFF
        self._frame_buffer: Deque[CameraFrame] = deque(
            maxlen=self.config.max_frame_buffer
        )
        self._frame_counter: int = 0
        self._recent_frames: List[CameraFrame] = []
        self.metrics = CameraMetrics()

    async def start(self):
        """标记摄像头为活跃（实际采集由前端 getUserMedia 完成）"""
        logger.info("Camera source starting...")
        self.state = CameraState.STARTING
        self.metrics = CameraMetrics(start_time=time.time())
        self.state = CameraState.ACTIVE
        logger.info("Camera source active")

    async def stop(self):
        """停止摄像头"""
        logger.info(
            "Camera source stopping (frames=%d, dropped=%d, errors=%d)",
            self.metrics.frames_received,
            self.metrics.frames_dropped,
            self.metrics.errors,
        )
        self.state = CameraState.OFF
        self._frame_buffer.clear()
        self._recent_frames.clear()
        logger.info("Camera source stopped")

    def receive_frame(self, data_base64: str, width: int = 640,
                      height: int = 480, format: str = "jpeg") -> Optional[CameraFrame]:
        """接收前端发来的帧"""
        if self.state != CameraState.ACTIVE:
            logger.debug("Camera not active, dropping frame")
            self.metrics.frames_dropped += 1
            return None

        self._frame_counter += 1
        now = time.time()

        frame = CameraFrame(
            frame_id=self._frame_counter,
            timestamp=now,
            width=width,
            height=height,
            data_base64=data_base64,
            format=format,
            size_bytes=len(data_base64) if data_base64 else 0,
        )

        self._frame_buffer.append(frame)
        self._recent_frames.append(frame)
        self.metrics.frames_received += 1
        self.metrics.last_frame_time = now

        # 实时更新 FPS 估算
        elapsed = now - self.metrics.start_time
        if elapsed > 0:
            self.metrics.avg_fps = self.metrics.frames_received / elapsed

        return frame

    def get_latest_frame(self) -> Optional[CameraFrame]:
        """获取最新帧"""
        if self._frame_buffer:
            return self._frame_buffer[-1]
        return None

    def get_recent_frames(self, count: int = 3) -> List[CameraFrame]:
        """获取最近 N 帧"""
        return self._recent_frames[-count:]

    def get_frame_buffer_snapshot(self) -> List[CameraFrame]:
        return list(self._frame_buffer)

    def get_state(self) -> CameraState:
        return self.state

    def is_active(self) -> bool:
        return self.state == CameraState.ACTIVE

    def set_error(self, message: str):
        self.state = CameraState.ERROR
        self.metrics.errors += 1
        logger.error("Camera error: %s", message)

    def get_metrics(self) -> dict:
        return {
            "state": self.state.value,
            "frames_received": self.metrics.frames_received,
            "frames_dropped": self.metrics.frames_dropped,
            "avg_fps": round(self.metrics.avg_fps, 2),
            "uptime_sec": round(self.metrics.uptime_sec, 1),
            "errors": self.metrics.errors,
        }
