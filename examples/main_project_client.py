"""
main_project_client.py — AI VTuber 主项目 REST API 接入示例

演示主项目如何通过 REST API 使用 video-companion：
1. 检查健康状态
2. 启动会话
3. 查询状态
4. 发送文字输入（通过 WebSocket 更实用，但 REST 供参考）
5. 停止会话、获取摘要

用法:
    python examples/main_project_client.py

前置: 先启动 video-companion 服务
    python -m app.server
"""

import httpx
import json
import time

BASE_URL = "http://127.0.0.1:8001"


def main():
    client = httpx.Client(base_url=BASE_URL, timeout=10)

    print("=== AI VTuber Main Project Client ===\n")

    # 1. 健康检查
    print("[1/5] 健康检查...")
    r = client.get("/api/health")
    assert r.status_code == 200
    print(f"  -> {r.json()}\n")

    # 2. 查看状态
    print("[2/5] 查询系统状态...")
    r = client.get("/api/status")
    status = r.json()
    print(f"  服务: {status['service']} v{status['version']}")
    print(f"  模式: {status['project_mode']}")
    print(f"  授权: camera={status['consent']['camera']}, mic={status['consent']['microphone']}")
    print()

    # 3. 启动会话
    print("[3/5] 启动会话...")
    r = client.post("/api/session/start?persona_id=default")
    session = r.json()
    assert session["status"] == "started"
    print(f"  -> session_state={session['session_state']}\n")

    # 4. 会话应该为 active
    print("[4/5] 检查会话状态...")
    r = client.get("/api/session/status")
    session_status = r.json()
    print(f"  state={session_status['session_state']}, total_turns={session_status['total_turns']}")
    print()

    # 5. 停止会话
    print("[5/5] 停止会话，获取摘要...")
    r = client.post("/api/session/stop")
    result = r.json()
    assert result["status"] == "stopped"
    summary = result["summary"]
    print(f"  session_id: {summary['session_id']}")
    print(f"  persona: {summary['display_name']} ({summary['persona_name']})")
    print(f"  duration: {summary['duration_sec']:.1f}s")
    print(f"  turns: {summary['total_turns']}")
    print(f"  summary: {summary['summary_text']}")
    print(f"  topics: {summary['key_topics']}")
    print(f"  reply_mode: {summary['reply_mode']}")
    print()

    # 验证关键字段
    assert len(summary["summary_text"]) > 0, "summary_text must not be empty"
    assert "session_id" in summary
    assert summary["display_name"] == "澪"
    assert summary["persona_name"] == "Mio"
    assert summary["saved_locally"] == False

    print("=== 所有步骤通过 ===\n")
    print("主项目接入 REST 路径已验证。")
    print("实时对话请使用 WebSocket (见 main_project_websocket_client.py)。")


if __name__ == "__main__":
    main()
