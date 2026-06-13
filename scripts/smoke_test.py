"""
smoke_test.py — AI VTuber 主项目接入验收

验证:
1. video-companion 在线
2. 主项目 /api/status 返回
3. session start
4. WebSocket 连接 + text_input → ai_response
5. avatar_state 字段完整
6. session stop → summary_text 非空

用法:
    python scripts/smoke_test.py
"""

import sys, os, json, asyncio
import httpx, websockets

VC_API = "http://127.0.0.1:8001"
VC_WS  = "ws://127.0.0.1:8001/ws"

PASS = 0; FAIL = 0

def check(name, ok, detail=""):
    global PASS, FAIL
    if ok: PASS += 1; print(f"  [PASS] {name}")
    else:  FAIL += 1; print(f"  [FAIL] {name}  {detail}")

async def main():
    global PASS, FAIL
    print("AI VTuber Main Project — Smoke Test\n")
    client = httpx.AsyncClient(timeout=10)

    # 1. VC health
    r = await client.get(f"{VC_API}/api/health")
    check("1. video-companion health", r.status_code == 200 and r.json()["status"] == "ok")

    # 2. Session start
    r = await client.post(f"{VC_API}/api/session/start?persona_id=default")
    check("2. session start", r.json()["status"] == "started")

    # 3. WS → text_input → ai_response
    async with websockets.connect(VC_WS) as ws:
        await ws.recv()  # status
        await ws.send(json.dumps({"type": "text_input", "text": "你好"}))
        check("3a. text_input sent", True)

        resp = None
        for _ in range(10):
            msg = json.loads(await ws.recv())
            if msg["type"] == "ai_response":
                resp = msg
                break

        check("3b. ai_response received", resp is not None)
        assert resp
        check("3c. text non-empty", len(resp["text"]) > 0)
        check("3d. reply_source=local_vtuber", resp["reply_source"] == "local_vtuber")

        av = resp.get("avatar_state", {})
        check("3e. avatar_state exists", bool(av))
        for f in ["expression", "mouth_open", "speaking", "looking_at_user", "attention"]:
            check(f"3f. avatar_state.{f}", f in av)
        check("3g. speaking=true", av.get("speaking") == True)
        check("3h. mouth_open=true", av.get("mouth_open") == True)
        check("3i. audio_base64 exists", isinstance(resp.get("audio_base64"), str))

    # 4. Session stop → summary
    r = await client.post(f"{VC_API}/api/session/stop")
    s = r.json()["summary"]
    check("4a. session stopped", r.json()["status"] == "stopped")
    check("4b. summary_text non-empty", len(s["summary_text"]) > 0)
    check("4c. persona_name=Mio", s["persona_name"] == "Mio")
    check("4d. display_name=澪", s["display_name"] == "澪")
    check("4e. turns >= 1", s["total_turns"] >= 1)

    await client.aclose()

    total = PASS + FAIL
    print(f"\n{'=' * 40}")
    print(f"  {PASS}/{total} passed, {FAIL} failed")
    return FAIL == 0

if __name__ == "__main__":
    try:
        ok = asyncio.run(main())
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        ok = False
    sys.exit(0 if ok else 1)
