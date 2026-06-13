"""
验证 Legacy Bridge（历史 Project Mnemosyne 桥接）

默认关闭。仅在 legacy_bridge.enabled=true 时使用。
"""

import sys
import os
import json

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def load_config():
    config_path = os.environ.get("VC_CONFIG", "config.yaml")
    if not os.path.exists(config_path):
        return {"legacy_bridge": {"api_base": "http://127.0.0.1:8000", "enabled": False}}

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        lb = cfg.get("legacy_bridge", cfg.get("mnemosyne", {}))
        return {"legacy_bridge": lb}
    except ImportError:
        return {"legacy_bridge": {"api_base": "http://127.0.0.1:8000", "enabled": False}}


def check_connection(api_base: str, timeout: int = 10) -> bool:
    print(f"[INFO] 检查 Legacy Bridge 连接: {api_base}")

    if not HAS_REQUESTS:
        print("[SKIP] requests 库未安装: pip install requests")
        return False

    try:
        resp = requests.get(f"{api_base}/", timeout=timeout)
        print(f"[OK] 响应: HTTP {resp.status_code}")
        return True
    except requests.ConnectionError:
        print("[FAIL] 无法连接 - 服务可能未启动")
        return False
    except requests.Timeout:
        print(f"[FAIL] 连接超时 ({timeout}s)")
        return False
    except Exception as e:
        print(f"[FAIL] 连接错误: {e}")
        return False


def main():
    print("=" * 50)
    print("Video Companion - Legacy Bridge 验证")
    print("=" * 50)

    config = load_config()
    lb_cfg = config.get("legacy_bridge", {})
    enabled = lb_cfg.get("enabled", False)
    api_base = lb_cfg.get("api_base", "http://127.0.0.1:8000")

    if not enabled:
        print("\n[INFO] Legacy bridge 已关闭 (legacy_bridge.enabled=false)。")
        print("[INFO] 当前项目以 standalone AI VTuber 模式运行，不需要此桥接。")
        return 0

    print(f"\nLegacy bridge 地址: {api_base}")
    connection_ok = check_connection(api_base)

    print("\n" + "=" * 50)
    print(f"Legacy bridge 连通: {'PASS' if connection_ok else 'FAIL'}")
    print("[INFO] 桥接不可达时，AI VTuber 仍可独立运行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
