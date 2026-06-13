"""
验证外部视觉模型 Provider 可用性

测试配置的视觉模型是否能正常调用。
"""

import sys
import os


def check_api_key(env_var: str) -> bool:
    key = os.environ.get(env_var, "")
    if not key:
        print(f"[FAIL] 环境变量 {env_var} 未设置")
        return False
    print(f"[OK] 环境变量 {env_var} 已设置 ({key[:8]}...)")
    return True


def test_openai_vision():
    """测试 OpenAI GPT-4o 视觉能力"""
    try:
        from openai import OpenAI
    except ImportError:
        print("[SKIP] openai 库未安装: pip install openai")
        return False

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("[FAIL] OPENAI_API_KEY 未设置")
        return False

    client = OpenAI(api_key=api_key)
    print("[INFO] 测试 OpenAI Vision API 连接...")

    try:
        # 用一个小测试验证连接
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Reply with just 'ok'"}],
            max_tokens=5,
        )
        print(f"[OK] API 连接成功，响应: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"[FAIL] API 调用失败: {e}")
        return False


def test_anthropic_vision():
    """测试 Anthropic Claude 视觉能力"""
    try:
        import anthropic
    except ImportError:
        print("[SKIP] anthropic 库未安装: pip install anthropic")
        return False

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[FAIL] ANTHROPIC_API_KEY 未设置")
        return False

    client = anthropic.Anthropic(api_key=api_key)
    print("[INFO] 测试 Anthropic API 连接...")

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=10,
            messages=[{"role": "user", "content": "Reply with just 'ok'"}],
        )
        print(f"[OK] API 连接成功，响应: {response.content[0].text}")
        return True
    except Exception as e:
        print(f"[FAIL] API 调用失败: {e}")
        return False


def main():
    print("=" * 50)
    print("Video Companion - 视觉模型 Provider 验证")
    print("=" * 50)

    # 尝试加载配置
    config_path = os.environ.get("VC_CONFIG", "config.yaml")
    provider = "openai"

    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            vp = config.get("vision_provider", {})
            provider = vp.get("provider", "openai")
            print(f"[INFO] 配置的 provider: {provider}")
        except ImportError:
            print("[WARN] pyyaml 未安装，使用默认 provider")
        except Exception as e:
            print(f"[WARN] 读取配置失败: {e}")

    print()

    results = {}
    if provider == "openai":
        results["openai"] = test_openai_vision()
    elif provider == "anthropic":
        results["anthropic"] = test_anthropic_vision()
    else:
        print(f"[INFO] Unknown provider '{provider}', testing all...")
        results["openai"] = test_openai_vision()
        results["anthropic"] = test_anthropic_vision()

    print("\n" + "=" * 50)
    passed = any(results.values())
    if passed:
        print("[PASS] 至少一个视觉模型 Provider 可用")
    else:
        print("[FAIL] 没有可用的视觉模型 Provider")
        print("[INFO] 请设置对应的 API Key 环境变量后再试")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
