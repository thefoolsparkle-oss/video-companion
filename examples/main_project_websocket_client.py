#!/usr/bin/env python
"""
main_project_websocket_client.py — AI VTuber 主项目 WebSocket 接入示例

演示主项目如何通过 WebSocket 与 video-companion 实时通信：
1. 连接 WebSocket
2. 启动会话 (REST)
3. 发送 text_input
4. 接收 ai_response（含 avatar_state）
5. 接收 transcript
6. 发送 ping 心跳
7. 停止会话

用法:
    pip install websockets httpx
    python examples/main_project_websocket_client.py

前置: 先启动 video-companion 服务
    python -m app.server
"""

import asyncio
import json
import httpx
import websockets

BASE_URL = "http://127.0.0.1:8001"
WS_URL = "ws://127.0.0.1:8001/ws"


async def main():
    print("=== AI VTuber WebSocket Client ===\n")

    client = httpx.AsyncClient(base_url=BASE_URL, timeout=10)

    # 1. 启动会话
    print("[1] 启动会话...")
    r = await client.post("/api/session/start?persona_id=default")
    assert r.json()["status"] == "started"
    print("  -> session started\n")

    # 2. 连接 WebSocket
    print("[2] 连接 WebSocket...")
    async with websockets.connect(WS_URL) as ws:
        # 接收初始 status
        init = json.loads(await ws.recv())
        assert init["type"] == "status"
        print(f"  -> connected, service={init['data']['service']}")

        # 3. 发送 text_input
        print("\n[3] 发送 text_input: '你好，我是主项目'\n")
        await ws.send(json.dumps({
            "type": "text_input",
            "text": "你好，我是主项目",
        }))

        # 4. 接收 ai_response 和 transcript
        messages = []
        for _ in range(4):
            msg = json.loads(await ws.recv())
            messages.append(msg)

            if msg["type"] == "ai_response":
                print(f"  [ai_response  #{msg['turn_id']}]")
                print(f"    text:          {msg['text']}")
                print(f"    reply_source:  {msg['reply_source']}")
                print(f"    audio_base64:  {'<data>' if msg['audio_base64'] else '(empty)'}")
                print(f"    asr_source:    {msg['asr_source']}")
                print(f"    latency:       {msg['total_latency_ms']}ms")

                avatar = msg["avatar_state"]
                print(f"    avatar_state:")
                print(f"      expression: {avatar['expression']}")
                print(f"      speaking:   {avatar['speaking']}")
                print(f"      mouth_open: {avatar['mouth_open']}")
                print(f"      attention:  {avatar['attention']}")

                # 验证关键字段
                assert isinstance(msg["text"], str) and len(msg["text"]) > 0
                assert "avatar_state" in msg
                assert msg["reply_source"] == "local_vtuber"
                assert msg["turn_id"] >= 1

            elif msg["type"] == "transcript":
                print(f"  [transcript #{msg['turn_id']}] {msg['speaker']}: {msg['text']}")

        print()

        # 5. 发送 ping
        print("[4] 发送 ping...")
        await ws.send(json.dumps({"type": "ping"}))
        pong = json.loads(await ws.recv())
        assert pong["type"] == "pong"
        print("  -> pong received\n")

    # 6. 停止会话
    print("[5] 停止会话...")
    r = await client.post("/api/session/stop")
    result = r.json()
    summary = result["summary"]
    print(f"  -> stopped, {summary['total_turns']} turns, duration={summary['duration_sec']:.1f}s")
    print(f"  -> summary: {summary['summary_text']}")

    assert summary["total_turns"] >= 1
    assert len(summary["summary_text"]) > 0

    print("\n=== 所有步骤通过 ===")
    print("主项目 WebSocket 接入路径已验证。")

    await http_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
