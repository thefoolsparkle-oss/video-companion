"""
verify_standalone.py — AI VTuber standalone 模式验证脚本

验证 video-companion 在无外部依赖下的核心闭环：
1. app 可以创建
2. /api/health 正常
3. /api/session/start 正常
4. /api/consent 默认全关
5. text turn 可以走 local_vtuber
6. session stop 返回 summary_text

用法:
    python scripts/verify_standalone.py

前置: 先启动 video-companion 服务
    python -m app.server
"""

import sys
import time
import json
import asyncio
import httpx
import websockets

BASE_URL = "http://127.0.0.1:8001"
WS_URL = "ws://127.0.0.1:8001/ws"

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


async def main():
    global PASS, FAIL

    print("=" * 50)
    print("Video Companion — Standalone Verification")
    print("=" * 50)

    client = httpx.AsyncClient(base_url=BASE_URL, timeout=10)

    # 1. Health check
    print("\n[1] Health check")
    try:
        r = await client.get("/api/health")
        check("Health endpoint returns 200", r.status_code == 200)
        check("Health returns status ok", r.json().get("status") == "ok")
    except Exception as e:
        check("Health endpoint reachable", False, str(e))
        print("Make sure video-companion is running: python -m app.server")
        await client.aclose()
        return

    # 2. System status
    print("\n[2] System status")
    r = await client.get("/api/status")
    status = r.json()
    check("status service is Video Companion", status["service"] == "Video Companion")
    check("project_mode is standalone", status["project_mode"] == "standalone_ai_vtuber")

    # 3. Consent defaults — all off
    print("\n[3] Consent defaults (all off)")
    r = await client.get("/api/consent")
    consent = r.json()
    check("camera default off", consent["camera"] == False)
    check("microphone default off", consent["microphone"] == False)
    check("external_vision default off", consent["external_vision"] == False)

    # 4. Start session
    print("\n[4] Session start")
    r = await client.post("/api/session/start?persona_id=default")
    check("session start returns started", r.json()["status"] == "started")

    r = await client.get("/api/session/status")
    check("session is active after start", r.json()["session_state"] == "active")

    # 5. Text turn via WebSocket — local_vtuber reply
    print("\n[5] Text turn (local_vtuber reply)")
    async with websockets.connect(WS_URL) as ws:
        # Consume initial status
        init = json.loads(await ws.recv())
        check("WS initial status received", init["type"] == "status")

        # Send text_input
        await ws.send(json.dumps({"type": "text_input", "text": "你好"}))
        check("text_input sent", True)

        # Collect messages until we get ai_response
        got_response = False
        got_transcript_user = False
        got_transcript_ai = False
        reply_source = None

        for _ in range(5):
            msg = json.loads(await ws.recv())

            if msg["type"] == "ai_response":
                got_response = True
                reply_source = msg.get("reply_source")
                check("ai_response has text", isinstance(msg.get("text"), str) and len(msg["text"]) > 0)
                check("ai_response has avatar_state", "avatar_state" in msg)
                check("ai_response reply_source", msg.get("reply_source") in ("local_vtuber", "legacy_bridge"))
                av = msg["avatar_state"]
                check("avatar_state has expression", "expression" in av)
                check("avatar_state has mouth_open", "mouth_open" in av)
                check("avatar_state has speaking", "speaking" in av)

            elif msg["type"] == "transcript":
                if msg["speaker"] == "user":
                    got_transcript_user = True
                elif msg["speaker"] == "ai":
                    got_transcript_ai = True

        check("received ai_response", got_response)
        check("reply_source is local_vtuber", reply_source == "local_vtuber")
        check("received user transcript", got_transcript_user)
        check("received AI transcript", got_transcript_ai)

    # 6. Stop session — get summary_text
    print("\n[6] Session stop & summary")
    r = await client.post("/api/session/stop")
    result = r.json()
    check("session stop returns stopped", result["status"] == "stopped")

    summary = result.get("summary", {})
    check("summary has session_id", "session_id" in summary)
    check("summary has persona_name", summary.get("persona_name") == "Mio")
    check("summary has display_name", summary.get("display_name") == "澪")
    check("summary_text is non-empty", len(summary.get("summary_text", "")) > 0)
    check("saved_locally is false", summary.get("saved_locally") == False)

    # 7. Camera / audio metrics accessible
    print("\n[7] Metrics endpoints")
    r = await client.get("/api/camera/metrics")
    check("camera metrics accessible", r.status_code == 200)
    r = await client.get("/api/audio/metrics")
    check("audio metrics accessible", r.status_code == 200)
    r = await client.get("/api/vision/usage")
    check("vision usage accessible", r.status_code == 200)

    await client.aclose()

    # Summary
    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"  RESULT: {PASS}/{total} passed, {FAIL} failed")
    print(f"{'=' * 50}")

    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
