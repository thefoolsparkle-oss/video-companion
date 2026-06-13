"""
main.py — AI VTuber 主项目入口

功能:
1. 检查 video-companion 是否运行
2. 如未运行，作为子进程启动 video-companion
3. 启动主项目 Web 服务器，提供前端页面
4. 提供 /api/status 代理端点

用法:
    pip install fastapi uvicorn
    python main.py
    → http://127.0.0.1:9000
"""

import sys
import os
import time
import signal
import subprocess
import logging
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VC_PATH = ROOT.parent / "video-companion"
WEB_PATH = ROOT / "web"

VC_HOST = "127.0.0.1"
VC_PORT = 8001
MAIN_HOST = "127.0.0.1"
MAIN_PORT = 9000

logging.basicConfig(level=logging.INFO, format="%(asctime)s [main] %(message)s")
log = logging.getLogger("ai-vtuber-main")

vc_process = None


def check_vc_health() -> bool:
    """检查 video-companion 是否在线"""
    try:
        url = f"http://{VC_HOST}:{VC_PORT}/api/health"
        resp = urllib.request.urlopen(url, timeout=2)
        return resp.status == 200
    except Exception:
        return False


def start_video_companion():
    """作为子进程启动 video-companion"""
    global vc_process
    if not VC_PATH.exists():
        log.error("video-companion not found at %s", VC_PATH)
        return False

    log.info("Starting video-companion from %s ...", VC_PATH)
    vc_process = subprocess.Popen(
        [sys.executable, "-m", "app.server"],
        cwd=str(VC_PATH),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 等待就绪
    deadline = time.time() + 15
    while time.time() < deadline:
        if check_vc_health():
            log.info("video-companion ready at %s:%s", VC_HOST, VC_PORT)
            return True
        time.sleep(0.5)

    log.error("video-companion did not become ready")
    return False


def ensure_vc():
    """确保 video-companion 可用"""
    if check_vc_health():
        log.info("video-companion already running at %s:%s", VC_HOST, VC_PORT)
        return True
    return start_video_companion()


def cleanup():
    """关闭子进程"""
    global vc_process
    if vc_process:
        log.info("Stopping video-companion...")
        vc_process.terminate()
        try:
            vc_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            vc_process.kill()
        log.info("video-companion stopped")


def create_app():
    """创建 FastAPI 应用"""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    import httpx

    app = FastAPI(title="AI VTuber Main Project", version="0.1.0-dev")

    # 静态文件
    if WEB_PATH.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_PATH)), name="static")

    @app.get("/")
    async def root():
        index_path = WEB_PATH / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"service": "AI VTuber Main Project", "version": "0.1.0-dev"}

    @app.get("/api/status")
    async def main_status():
        vc_ok = check_vc_health()
        return {
            "service": "AI VTuber Main Project",
            "version": "0.1.0-dev",
            "video_companion": {
                "host": f"{VC_HOST}:{VC_PORT}",
                "online": vc_ok,
            },
            "server": {
                "host": f"{MAIN_HOST}:{MAIN_PORT}",
            },
        }

    return app


async def main():
    log.info("=" * 50)
    log.info("AI VTuber Main Project v0.1.0-dev")
    log.info("=" * 50)

    # 确保 video-companion
    if not ensure_vc():
        log.error("Cannot start without video-companion")
        sys.exit(1)

    # 注册退出清理
    signal.signal(signal.SIGINT, lambda s, f: (cleanup(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (cleanup(), sys.exit(0)))

    # 启动 Web 服务
    try:
        import uvicorn
    except ImportError:
        log.error("uvicorn not installed: pip install uvicorn")
        sys.exit(1)

    app = create_app()
    log.info("Starting web server at http://%s:%s", MAIN_HOST, MAIN_PORT)
    log.info("Open your browser and go to: http://%s:%s", MAIN_HOST, MAIN_PORT)

    config = uvicorn.Config(app, host=MAIN_HOST, port=MAIN_PORT, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cleanup()
