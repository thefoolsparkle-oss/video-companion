"""
smoke_test.py — AI VTuber 主项目真实接入冒烟测试

启动 video-companion 服务，通过 WebSocket 发送 text_input，
验证收到完整的 ai_response (text/audio_base64/avatar_state/reply_source)，
然后 stop session 并检查 summary_text 非空。

用法:
    python scripts/smoke_test.py

自动启动服务，无需额外步骤。
"""

import sys
import os
import json
import time
import asyncio
import threading
import uvicorn
import httpx
import websockets

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

BASE_URL = "http://127.0.0.1:8001"
WS_URL = "ws://127.0.0.1:8001/ws"

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def start_server():
    """在后台线程启动 uvicorn"""
    from app.server import VideoCompanionServer, create_app

    server = VideoCompanionServer()
    app = create_app(server)

    cfg = uvicorn.Config(app, host="127.0.0.1", port=8001, log_level="warning")
    srv = uvicorn.Server(cfg)

    async def serve():
        await srv.serve()

    thread = threading.Thread(target=lambda: asyncio.run(serve()), daemon=True)
    thread.start()
    time.sleep(1.5)
    return srv


async def recv_with_timeout(ws, timeout: float = 3.0) -> dict | None:
    """接收一条消息，超时返回 None"""
    try:
        return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
    except asyncio.TimeoutError:
        return None


async def run_smoke():
    global PASS, FAIL

    print("=" * 50)
    print("AI VTuber Smoke Test — Real Integration")
    print("=" * 50)

    # 1. Start server
    print("\n[1] Starting video-companion server...")
    server = start_server()

    client = httpx.AsyncClient(base_url=BASE_URL, timeout=10)

    # 2. Wait for health
    print("[2] Waiting for /api/health...")
    for i in range(20):
        try:
            r = await client.get("/api/health")
            if r.status_code == 200:
                break
        except Exception:
            await asyncio.sleep(0.3)
    else:
        check("Server started and healthy", False, "Timeout")
        await client.aclose()
        return

    r = await client.get("/api/health")
    check("Health returns ok", r.json()["status"] == "ok")

    # 3. Start session
    print("\n[3] Start session...")
    r = await client.post("/api/session/start?persona_id=default")
    check("Session started", r.json()["status"] == "started")
    payload = r.json()
    check("Session state is active", payload["session_state"] == "active")
    check("Persona is default", payload["persona_id"] == "default")

    # 4. WebSocket: send text_input, receive ai_response
    print("\n[4] WebSocket text_input → ai_response...")
    async with websockets.connect(WS_URL, close_timeout=3) as ws:
        init = await recv_with_timeout(ws)
        check("WS initial status received", init is not None and init.get("type") == "status")

        await ws.send(json.dumps({"type": "text_input", "text": "你好"}))
        check("text_input sent", True)

        ai_response = None
        transcript_user = False
        transcript_ai = False

        # 收集消息直到拿到 ai_response 和 transcripts，最多等 10 条
        for _ in range(10):
            msg = await recv_with_timeout(ws, timeout=2.0)
            if msg is None:
                break
            if msg["type"] == "ai_response":
                ai_response = msg
            elif msg["type"] == "transcript":
                if msg["speaker"] == "user":
                    transcript_user = True
                elif msg["speaker"] == "ai":
                    transcript_ai = True
            if ai_response and transcript_user and transcript_ai:
                break

        check("ai_response received", ai_response is not None)
        assert ai_response is not None

        check("ai_response.text non-empty",
              isinstance(ai_response.get("text"), str) and len(ai_response["text"]) > 0)
        check("ai_response.reply_source is local_vtuber",
              ai_response.get("reply_source") == "local_vtuber")
        check("ai_response.audio_base64 present",
              isinstance(ai_response.get("audio_base64"), str))
        check("ai_response has turn_id",
              isinstance(ai_response.get("turn_id"), int) and ai_response["turn_id"] >= 1)

        av = ai_response.get("avatar_state")
        check("ai_response has avatar_state", av is not None)
        assert av is not None
        for field in ["expression", "mouth_open", "speaking", "looking_at_user", "attention"]:
            check(f"avatar_state.{field} present", field in av)

        check("avatar_state.speaking is True", av.get("speaking") == True)
        check("avatar_state.mouth_open is True", av.get("mouth_open") == True)
        check("avatar_state.expression is talking", av.get("expression") == "talking")

        check("transcript user received", transcript_user)
        check("transcript AI received", transcript_ai)

    # 5. Stop session
    print("\n[5] Stop session & check summary...")
    r = await client.post("/api/session/stop")
    result = r.json()
    check("Stop returns stopped", result["status"] == "stopped")

    summary = result.get("summary", {})
    check("summary has session_id", "session_id" in summary)
    check("summary_text non-empty", len(summary.get("summary_text", "")) > 0)
    check("summary has persona_name", summary.get("persona_name") == "Mio")
    check("summary has display_name", summary.get("display_name") == "澪")
    check("summary total_turns >= 1", summary.get("total_turns", 0) >= 1)
    check("summary reply_mode standalone", summary.get("reply_mode") == "standalone_ai_vtuber")
    check("summary saved_locally is False", summary.get("saved_locally") == False)

    await client.aclose()

    # Shutdown
    try:
        server.should_exit = True
    except Exception:
        pass

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"  RESULT: {PASS}/{total} passed, {FAIL} failed")
    print(f"{'=' * 50}")

    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(run_smoke())
    sys.exit(0 if ok else 1)
