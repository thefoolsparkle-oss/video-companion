# Video Companion Test Suite Runner — AI VTuber Standalone Mode
# 运行所有模块测试
# 用法: python run_tests.py

import sys
import os
import time
import traceback

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

import logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("video-companion").setLevel(logging.WARNING)


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = 0
        self.failures = []

    def add_pass(self):
        self.passed += 1

    def add_fail(self, test_name: str, error: str):
        self.failed += 1
        self.failures.append((test_name, error))

    def add_error(self, test_name: str, error: str):
        self.errors += 1
        self.failures.append((test_name, f"ERROR: {error}"))

    @property
    def total(self):
        return self.passed + self.failed + self.errors

    @property
    def ok(self):
        return self.failed == 0 and self.errors == 0


class TestRunner:
    def __init__(self):
        self.results = []

    def run_module(self, name: str, module):
        result = TestResult(name)
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")

        tests = [m for m in dir(module) if m.startswith("test_")]
        for test_name in sorted(tests):
            fn = getattr(module, test_name)
            if not callable(fn):
                continue
            try:
                fn()
                result.add_pass()
                print(f"  [PASS] {test_name}")
            except AssertionError as e:
                result.add_fail(test_name, str(e))
                print(f"  [FAIL] {test_name}: {e}")
            except Exception as e:
                result.add_error(test_name, str(e))
                print(f"  [ERROR] {test_name}: {e}")
                traceback.print_exc()

        self.results.append(result)
        print(f"  --- {result.passed} passed, {result.failed} failed, {result.errors} errors ---")

    def summary(self):
        print(f"\n{'='*60}")
        print(f"  OVERALL SUMMARY")
        print(f"{'='*60}")
        total_pass = sum(r.passed for r in self.results)
        total_fail = sum(r.failed for r in self.results)
        total_err = sum(r.errors for r in self.results)
        total = total_pass + total_fail + total_err

        for r in self.results:
            status = "OK" if r.ok else "FAIL"
            print(f"  [{status}] {r.name}: {r.passed}/{r.total}")

        print(f"\n  TOTAL: {total_pass} passed, {total_fail} failed, {total_err} errors")
        return total_fail == 0 and total_err == 0


def main():
    from tests import test_consent
    from tests import test_camera_source
    from tests import test_audio_source
    from tests import test_local_vision
    from tests import test_vision_provider
    from tests import test_speech_provider
    from tests import test_media_session
    from tests import test_mnemosyne_client
    from tests import test_rest_api
    from tests import test_video_turn_contract
    from tests import test_avatar_state
    from tests import test_api_contract
    from tests import test_integration_standalone

    runner = TestRunner()

    runner.run_module("test_consent", test_consent)
    runner.run_module("test_camera_source", test_camera_source)
    runner.run_module("test_audio_source", test_audio_source)
    runner.run_module("test_local_vision", test_local_vision)
    runner.run_module("test_vision_provider", test_vision_provider)
    runner.run_module("test_speech_provider", test_speech_provider)
    runner.run_module("test_media_session", test_media_session)
    runner.run_module("test_mnemosyne_client", test_mnemosyne_client)
    runner.run_module("test_rest_api", test_rest_api)
    runner.run_module("test_video_turn_contract", test_video_turn_contract)
    runner.run_module("test_avatar_state", test_avatar_state)
    runner.run_module("test_api_contract", test_api_contract)
    runner.run_module("test_integration_standalone", test_integration_standalone)

    ok = runner.summary()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
