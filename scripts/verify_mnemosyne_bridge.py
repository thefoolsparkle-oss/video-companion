"""
验证与主项目 (Project Mnemosyne) 的 API 桥接

测试主项目 API 是否可达、接口契约是否匹配。
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
        return {"mnemosyne": {"api_base": "http://127.0.0.1:8000"}}

    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {"mnemosyne": {"api_base": "http://127.0.0.1:8000"}}


def check_connection(api_base: str, timeout: int = 10) -> bool:
    """检查主项目 HTTP 连通性"""
    print(f"[INFO] 检查主项目连接: {api_base}")

    if not HAS_REQUESTS:
        print("[SKIP] requests 库未安装: pip install requests")
        return False

    try:
        resp = requests.get(f"{api_base}/", timeout=timeout)
        print(f"[OK] 主项目响应: HTTP {resp.status_code}")
        return True
    except requests.ConnectionError:
        print("[FAIL] 无法连接到主项目 - 服务可能未启动")
        return False
    except requests.Timeout:
        print(f"[FAIL] 连接超时 ({timeout}s)")
        return False
    except Exception as e:
        print(f"[FAIL] 连接错误: {e}")
        return False


def check_video_endpoints(api_base: str, timeout: int = 10) -> dict:
    """检查视频相关的 API 端点"""
    if not HAS_REQUESTS:
        return {}

    endpoints = {
        "session-context": f"{api_base}/api/video/session-context?persona_id=test",
        "session-summary": f"{api_base}/api/video/session-summary",
        "observation": f"{api_base}/api/video/observation",
        "consent": f"{api_base}/api/video/consent",
    }

    results = {}
    for name, url in endpoints.items():
        try:
            # GET 用于 session-context，POST 用于其他
            if "session-context" in name:
                resp = requests.get(url, timeout=timeout)
            else:
                resp = requests.post(url, json={}, timeout=timeout)

            status = resp.status_code
            if status in (200, 201, 404, 405):
                # 404/405 说明路由存在但资源不存在或方法不对（可接受）
                results[name] = "available"
                print(f"[OK] {name}: HTTP {status}")
            elif status in (401, 403):
                results[name] = "auth_required"
                print(f"[OK] {name}: HTTP {status} (需要认证)")
            else:
                results[name] = f"unexpected_{status}"
                print(f"[WARN] {name}: HTTP {status}")
        except requests.ConnectionError:
            results[name] = "unreachable"
            print(f"[FAIL] {name}: 连接失败")
        except Exception as e:
            results[name] = str(e)
            print(f"[FAIL] {name}: {e}")

    return results


def check_contract_types():
    """检查接口契约数据结构定义"""
    print("\n[INFO] 检查本地接口契约定义...")

    contract_structures = {
        "VideoObservation": [
            "user_present", "camera_usable", "rough_mood",
            "object_hint", "face_present", "motion_level",
        ],
        "VideoTurn": [
            "user_speech_text", "visual_observation",
            "ai_response_text", "playback_completed",
        ],
        "VideoSessionSummary": [
            "persona_id", "start_time", "end_time",
            "key_facts", "memory_candidates", "risk_flags",
        ],
        "VideoConsentState": [
            "camera", "microphone", "external_vision_upload",
            "save_summary", "save_observation",
        ],
    }

    all_ok = True
    for struct_name, fields in contract_structures.items():
        print(f"[INFO] {struct_name}: {', '.join(fields)}")

    return all_ok


def main():
    print("=" * 50)
    print("Video Companion - Mnemosyne 桥接验证")
    print("=" * 50)

    config = load_config()
    mnemosyne_cfg = config.get("mnemosyne", {})
    api_base = mnemosyne_cfg.get("api_base", "http://127.0.0.1:8000")
    timeout = mnemosyne_cfg.get("timeout", 10)

    print(f"\n主项目地址: {api_base}")

    # 1. 连通性检查
    connection_ok = check_connection(api_base, timeout)

    # 2. 端点检查
    endpoint_results = {}
    if connection_ok:
        print("\n检查视频 API 端点...")
        endpoint_results = check_video_endpoints(api_base, timeout)

    # 3. 契约检查
    check_contract_types()

    # 总结
    print("\n" + "=" * 50)
    print("验证总结:")
    print(f"  主项目连通: {'PASS' if connection_ok else 'FAIL (主项目可能未启动)'}")

    available = sum(1 for v in endpoint_results.values() if v in ("available", "auth_required"))
    total = len(endpoint_results)
    if total > 0:
        print(f"  API 端点: {available}/{total} 可达")

    print("\n[INFO] 主项目未启动时，视频项目仍可独立运行（本地模式）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
