"""
用户授权管理模块 (V7 硬化版)

管理摄像头、麦克风、外部视觉模型上传等授权状态。
所有授权默认关闭，用户需分别明确开启。
特性：
- 分项独立授权
- 授权变更回调
- 审计日志
- PII 脱敏日志
- 状态序列化/反序列化
"""

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, Optional, List, Callable
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# PII 脱敏 —— 日志中不输出完整授权状态
def _safe_log(msg: str, **kwargs):
    """脱敏日志输出"""
    sanitized = {k: ("***" if v else v) for k, v in kwargs.items()}
    logger.info(msg, extra=sanitized)


class ConsentItem(str, Enum):
    CAMERA = "camera"
    MICROPHONE = "microphone"
    EXTERNAL_VISION = "external_vision"
    SAVE_SUMMARY = "save_summary"
    SAVE_OBSERVATION = "save_observation"

    @classmethod
    def all_items(cls) -> List["ConsentItem"]:
        return list(cls)

    @classmethod
    def media_items(cls) -> List["ConsentItem"]:
        """涉及媒体采集的授权项"""
        return [cls.CAMERA, cls.MICROPHONE]

    @classmethod
    def upload_items(cls) -> List["ConsentItem"]:
        """涉及外部上传的授权项"""
        return [cls.EXTERNAL_VISION]

    @classmethod
    def storage_items(cls) -> List["ConsentItem"]:
        """涉及数据存储的授权项"""
        return [cls.SAVE_SUMMARY, cls.SAVE_OBSERVATION]


@dataclass
class ConsentChange:
    """授权变更记录"""
    timestamp: str
    item: str
    old_value: bool
    new_value: bool
    reason: str = ""


@dataclass
class ConsentState:
    """用户授权状态"""
    camera: bool = False
    microphone: bool = False
    external_vision: bool = False
    save_summary: bool = False
    save_observation: bool = False

    def is_granted(self, item: ConsentItem) -> bool:
        return getattr(self, item.value, False)

    def is_any_media_active(self) -> bool:
        """是否有任何媒体采集开启"""
        return self.camera or self.microphone

    def is_any_upload_active(self) -> bool:
        """是否有任何外部上传开启"""
        return self.external_vision

    def grant(self, item: ConsentItem) -> bool:
        """授权，返回是否状态变更"""
        old = getattr(self, item.value)
        setattr(self, item.value, True)
        return old != True

    def revoke(self, item: ConsentItem) -> bool:
        """撤销，返回是否状态变更"""
        old = getattr(self, item.value)
        setattr(self, item.value, False)
        return old != False

    def to_dict(self) -> Dict[str, bool]:
        return asdict(self)

    def to_api_payload(self) -> dict:
        return {
            "camera": self.camera,
            "microphone": self.microphone,
            "external_vision_upload": self.external_vision,
            "save_summary": self.save_summary,
            "save_observation": self.save_observation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsentState":
        return cls(
            camera=data.get("camera", False),
            microphone=data.get("microphone", False),
            external_vision=data.get("external_vision", False),
            save_summary=data.get("save_summary", False),
            save_observation=data.get("save_observation", False),
        )


class ConsentManager:
    """授权管理器"""

    def __init__(self, defaults: Optional[Dict[str, bool]] = None,
                 enable_audit: bool = True,
                 audit_log_path: Optional[str] = None,
                 redact_pii: bool = True):
        defaults = defaults or {}
        self.state = ConsentState(
            camera=defaults.get("camera", False),
            microphone=defaults.get("microphone", False),
            external_vision=defaults.get("external_vision", False),
            save_summary=defaults.get("save_summary", False),
            save_observation=defaults.get("save_observation", False),
        )
        self._listeners: List[Callable] = []
        self._change_log: List[ConsentChange] = []
        self._enable_audit = enable_audit
        self._audit_log_path = audit_log_path
        self._redact_pii = redact_pii

        # 启动时授权日志
        if self._enable_audit:
            logger.info("ConsentManager initialized (defaults: all off)")

    def _record_change(self, item: ConsentItem, old_val: bool, new_val: bool,
                       reason: str = ""):
        """记录授权变更"""
        change = ConsentChange(
            timestamp=datetime.now(timezone.utc).isoformat(),
            item=item.value,
            old_value=old_val,
            new_value=new_val,
            reason=reason,
        )
        self._change_log.append(change)

        # 脱敏日志
        if self._redact_pii:
            _safe_log(
                f"Consent change: {item.value} {old_val}->{new_val}",
                **{item.value: new_val}
            )
        else:
            logger.info(
                "Consent changed: %s %s->%s reason=%s",
                item.value, old_val, new_val, reason
            )

        # 持久化审计日志
        if self._enable_audit and self._audit_log_path:
            self._append_audit_file(change)

        # 通知监听器
        for listener in self._listeners:
            try:
                listener(item, old_val, new_val)
            except Exception as e:
                logger.error("Consent listener error: %s", e)

    def _append_audit_file(self, change: ConsentChange):
        try:
            os.makedirs(os.path.dirname(self._audit_log_path) or ".", exist_ok=True)
            with open(self._audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(change), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    def on_change(self, callback: Callable):
        """注册授权变更回调"""
        self._listeners.append(callback)

    # ---- 便捷方法 ----

    def can_capture_camera(self) -> bool:
        return self.state.camera

    def can_capture_microphone(self) -> bool:
        return self.state.microphone

    def can_upload_to_vision_model(self) -> bool:
        return self.state.external_vision

    def can_save_summary(self) -> bool:
        return self.state.save_summary

    def can_save_observation(self) -> bool:
        return self.state.save_observation

    def can_capture_any_media(self) -> bool:
        return self.state.is_any_media_active()

    # ---- 单项变更 ----

    def _change_item(self, item: ConsentItem, value: bool, reason: str = ""):
        old = getattr(self.state, item.value)
        if old == value:
            return
        if value:
            self.state.grant(item)
        else:
            self.state.revoke(item)
        self._record_change(item, old, value, reason)

    def grant_camera(self, reason: str = ""):
        self._change_item(ConsentItem.CAMERA, True, reason)

    def revoke_camera(self, reason: str = ""):
        self._change_item(ConsentItem.CAMERA, False, reason)

    def grant_microphone(self, reason: str = ""):
        self._change_item(ConsentItem.MICROPHONE, True, reason)

    def revoke_microphone(self, reason: str = ""):
        self._change_item(ConsentItem.MICROPHONE, False, reason)

    def grant_external_vision(self, reason: str = ""):
        self._change_item(ConsentItem.EXTERNAL_VISION, True, reason)

    def revoke_external_vision(self, reason: str = ""):
        self._change_item(ConsentItem.EXTERNAL_VISION, False, reason)

    # ---- 批量操作 ----

    def revoke_all(self, reason: str = "session_end"):
        for item in ConsentItem.all_items():
            self._change_item(item, False, reason)

    def revoke_all_media(self, reason: str = ""):
        for item in ConsentItem.media_items():
            self._change_item(item, False, reason)

    def revoke_all_uploads(self, reason: str = ""):
        for item in ConsentItem.upload_items():
            self._change_item(item, False, reason)

    # ---- 查询 ----

    def get_state(self) -> ConsentState:
        return self.state

    def to_dict(self) -> Dict[str, bool]:
        return self.state.to_dict()

    def get_audit_log(self, limit: int = 50) -> List[dict]:
        return [asdict(c) for c in self._change_log[-limit:]]

    def is_privacy_safe(self) -> bool:
        """检查隐私安全状态 —— 所有敏感项关闭"""
        return not (self.state.camera or self.state.microphone or
                    self.state.external_vision)
