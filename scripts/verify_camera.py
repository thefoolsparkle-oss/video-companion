"""
验证摄像头可用性

检查本机摄像头是否能正常打开和捕获帧。
"""

import sys
import time


def check_opencv():
    """使用 OpenCV 检查摄像头"""
    try:
        import cv2
        print("[OK] OpenCV (cv2) 已安装")
    except ImportError:
        print("[SKIP] OpenCV 未安装，尝试其他方式...")
        return False

    print("\n正在打开默认摄像头...")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("[FAIL] 无法打开默认摄像头 (index 0)")
        # 尝试 index 1
        cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            print("[FAIL] 无法打开摄像头 (index 1)")
            return False
        print("[OK] 使用摄像头 index 1")

    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[INFO] 分辨率: {int(width)}x{int(height)}, FPS: {fps:.1f}")

    print("正在捕获测试帧...")
    for i in range(3):
        ret, frame = cap.read()
        if not ret:
            print(f"[FAIL] 第 {i+1} 次捕获失败")
            cap.release()
            return False
        print(f"[OK] 第 {i+1} 帧: {frame.shape}")
        time.sleep(0.5)

    cap.release()
    print("\n[PASS] 摄像头验证通过！")
    return True


def check_browser_hint():
    """提示浏览器端验证"""
    print("""
[提示] 浏览器端摄像头验证:
  1. 启动服务: python app/server.py
  2. 打开浏览器访问 http://localhost:8001
  3. 勾选"摄像头"授权
  4. 确认预览画面正常显示
""")


def main():
    print("=" * 50)
    print("Video Companion - 摄像头验证")
    print("=" * 50)

    result = check_opencv()

    if not result:
        print("\n[INFO] 后端摄像头检查未通过，但这不影响浏览器端使用。")
        print("[INFO] 浏览器端通过 getUserMedia 独立采集摄像头。")

    check_browser_hint()

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
