"""
smoke_test.py — AI VTuber 主项目接入验收

验证:
1. video-companion 在线
2. session start / WebSocket / text_input → ai_response
3. avatar_state / audio_base64 / reply_source
4. session stop → summary_text

注意:
  - 此测试验证 mock pipeline，不验证真实摄像头/麦克风
  - 真实 ASR/TTS 需要 API key 配置后才能验证
  - 摄像头/麦克风硬件需手动验证，见 HARDWARE_CHECK.md
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
    print("AI VTuber Main Project — Smoke Test")
    print("=" * 50)
    print()

    client = httpx.AsyncClient(timeout=10)

    # 1. VC health
    r = await client.get(f"{VC_API}/api/health")
    check("video-companion health", r.status_code == 200 and r.json()["status"] == "ok")

    # 2. Session start
    r = await client.post(f"{VC_API}/api/session/start?persona_id=default")
    check("session start", r.json()["status"] == "started")

    # 3. WS text_input → ai_response
    async with websockets.connect(VC_WS) as ws:
        await ws.recv()  # status
        await ws.send(json.dumps({"type": "text_input", "text": "你好"}))
        check("text_input sent", True)

        resp = None
        for _ in range(10):
            msg = json.loads(await ws.recv())
            if msg["type"] == "ai_response":
                resp = msg
                break

        check("ai_response received", resp is not None)
        assert resp
        check("text non-empty", len(resp["text"]) > 0)
        check("reply_source=local_vtuber", resp["reply_source"] == "local_vtuber")

        av = resp.get("avatar_state", {})
        check("avatar_state exists", bool(av))
        for f in ["expression", "mouth_open", "speaking", "looking_at_user", "attention"]:
            check(f"avatar_state.{f}", f in av)
        check("speaking=true", av.get("speaking") == True)
        check("mouth_open=true", av.get("mouth_open") == True)
        check("audio_base64 exists", isinstance(resp.get("audio_base64"), str))

    # 4. Session stop → summary
    r = await client.post(f"{VC_API}/api/session/stop")
    s = r.json()["summary"]
    check("session stopped", r.json()["status"] == "stopped")
    check("summary_text non-empty", len(s["summary_text"]) > 0)
    check("persona_name=Mio", s["persona_name"] == "Mio")
    check("display_name=澪", s["display_name"] == "澪")
    check("turns >= 1", s["total_turns"] >= 1)

    await client.aclose()

    # 诚实报告
    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"  Mock pipeline:    {PASS}/{total} passed")
    print(f"  Real camera:      not verified by automated test")
    print(f"  Real microphone:  not verified by automated test")
    print(f"  Real ASR/TTS:     not verified (needs API key)")
    print(f"{'=' * 50}")
    return FAIL == 0

if __name__ == "__main__":
    try:
        ok = asyncio.run(main())
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        ok = False
    sys.exit(0 if ok else 1)
