"""CRUX: Test suite for safe rate-limit parsing logic."""
import json
import subprocess
import sys

def run_jq(expr, input_data):
    if isinstance(input_data, dict):
        input_str = json.dumps(input_data)
    else:
        input_str = input_data
    result = subprocess.run(["jq", "-r", expr], input=input_str,
                          capture_output=True, text=True, timeout=10)
    return result.stdout.strip()

OLD_SHAPE = {"rate": {"limit": 5000, "remaining": 4500, "used": 500, "reset": 1000},
             "resources": {"core": {"limit": 5000, "remaining": 4500, "used": 500}}}
NEW_SHAPE = {"resources": {"core": {"limit": 5000, "remaining": 4300, "used": 700, "reset": 1000}}}
MISSING_CORE = {"rate": {"limit": 5000, "remaining": 4500, "used": 500, "reset": 1000}}
MISSING_REMAINING = {"resources": {"core": {"limit": 5000, "used": 500, "reset": 1000}}}
MISSING_RESET = {"resources": {"core": {"limit": 5000, "remaining": 100, "used": 4900}}}
EMPTY_SHAPE = {}
INVALID_JSON = "not valid json"

SAFE_REMAINING_EXPR = ".resources.core.remaining // .rate.remaining // empty"
SAFE_RESET_EXPR = ".resources.core.reset // .rate.reset // empty"

tests_passed = 0
tests_total = 0

def test(name, condition):
    global tests_passed, tests_total
    tests_total += 1
    if condition:
        print(f"  PASS - Test {tests_total}: {name}")
        tests_passed += 1
    else:
        print(f"  FAIL - Test {tests_total}: {name}")

test("old shape remaining = 4500", run_jq(SAFE_REMAINING_EXPR, OLD_SHAPE) == "4500")
test("new shape remaining = 4300", run_jq(SAFE_REMAINING_EXPR, NEW_SHAPE) == "4300")
test("missing resources.core falls back to rate.remaining = 4500", run_jq(SAFE_REMAINING_EXPR, MISSING_CORE) == "4500")
test("missing remaining returns empty (fail-safe)", run_jq(SAFE_REMAINING_EXPR, MISSING_REMAINING) == "")
test("missing reset returns empty (fail-safe)", run_jq(SAFE_RESET_EXPR, MISSING_RESET) == "")
test("empty shape returns empty (fail-safe)", run_jq(SAFE_REMAINING_EXPR, EMPTY_SHAPE) == "")
test("invalid JSON fails safely", subprocess.run(["jq", "-r", SAFE_REMAINING_EXPR], input=INVALID_JSON,
                       capture_output=True, text=True, timeout=10).returncode != 0)
test("low quota detected: remaining = 10", run_jq(SAFE_REMAINING_EXPR, {"resources": {"core": {"remaining": 10, "reset": 9999999999}}}) == "10")
test("new shape reset = 1000", run_jq(SAFE_RESET_EXPR, NEW_SHAPE) == "1000")

print()
print("=" * 60)
print(f"Test Results: {tests_passed}/{tests_total} tests passed")
print("=" * 60)

if tests_passed == tests_total:
    print("\nALL TESTS PASS - Safe parsing logic verified")
    sys.exit(0)
else:
    print(f"\n{tests_total - tests_passed} tests failed")
    sys.exit(1)
