#!/usr/bin/env bash
# CRUX: Test harness for check_rate_limit() shell function
# Tests the actual shell function with mocked curl responses
set -eo pipefail

# Put mock curl first in PATH (relative to project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PATH="$PROJECT_ROOT/scripts:$PATH"

# Source lib.sh from project scripts directory
source "$PROJECT_ROOT/scripts/lib.sh"

export ORG_PAT="mock_pat_token_for_testing"

# --- Test fixtures (inline JSON) ---
OLD_SHAPE='{"rate":{"limit":5000,"remaining":4500,"used":500,"reset":1000},"resources":{"core":{"limit":5000,"remaining":4500,"used":500}}}'
NEW_SHAPE='{"resources":{"core":{"limit":5000,"remaining":4300,"used":700,"reset":1000}}}'
MISSING_CORE='{"rate":{"limit":5000,"remaining":4500,"used":500,"reset":1000}}'
MISSING_REMAINING='{"resources":{"core":{"limit":5000,"used":500,"reset":1000}}}'
MISSING_RESET='{"resources":{"core":{"limit":5000,"remaining":100,"used":4900}}}'
EMPTY_SHAPE='{}'
INVALID_JSON='not valid json'

# Low quota: remaining=10, reset = now + 30 seconds (so wait_secs < 900)
NOW_EPOCH=$(date +%s)
RESET_SOON=$((NOW_EPOCH + 30))
LOW_QUOTA_SHAPE="{\"resources\":{\"core\":{\"remaining\":10,\"reset\":${RESET_SOON},\"used\":4990}}}"

tests_passed=0
tests_total=0

pass() { tests_passed=$((tests_passed+1)); echo "  PASS - Test $tests_total: $1"; }
fail() { echo "  FAIL - Test $tests_total: $1"; }

test() {
    tests_total=$((tests_total+1))
    local name="$1"; local code="$2"
    if eval "$code" 2>/dev/null; then pass "$name"; else fail "$name"; fi
}

setup_mock() {
    local b64_body
    # GNU base64 wraps at 76 columns; BSD/macOS does not. Strip newlines
    # so the mock-state file stays valid on every platform.
    b64_body="$(printf '%s' "$3" | base64 | tr -d '\n')"
    printf 'MOCK_CURL_FIXTURE=%s\n' "$1" > "$PROJECT_ROOT/.mock_state"
    printf 'MOCK_CURL_HTTP=%s\n' "$2" >> "$PROJECT_ROOT/.mock_state"
    printf 'MOCK_CURL_BODY_B64=%s\n' "$b64_body" >> "$PROJECT_ROOT/.mock_state"
}

# Clean up any leftover state
rm -f "$PROJECT_ROOT/.mock_state" "$PROJECT_ROOT/.mock_stderr"

# --- Test 1: Old response shape ---
test "old shape returns 4500" '
    setup_mock old_shape 200 "$OLD_SHAPE"
    result="$(check_rate_limit)"
    [ "$result" = "4500" ]
'

# --- Test 2: New response shape ---
test "new shape returns 4300" '
    setup_mock new_shape 200 "$NEW_SHAPE"
    result="$(check_rate_limit)"
    [ "$result" = "4300" ]
'

# --- Test 3: Missing resources.core falls back to rate ---
test "missing core falls back to rate.remaining" '
    setup_mock missing_core 200 "$MISSING_CORE"
    result="$(check_rate_limit)"
    [ "$result" = "4500" ]
'

# --- Test 4: Missing remaining returns 0 ---
test "missing remaining returns 0" '
    setup_mock missing_remaining 200 "$MISSING_REMAINING"
    result="$(check_rate_limit)"
    [ "$result" = "0" ]
'

# --- Test 5: Missing reset returns remaining (not 0) ---
test "missing reset returns remaining (not 0)" '
    setup_mock missing_reset 200 "$MISSING_RESET"
    result="$(check_rate_limit)"
    [ "$result" = "100" ]
'

# --- Test 6: Empty shape returns 0 ---
test "empty shape returns 0" '
    setup_mock empty 200 "$EMPTY_SHAPE"
    result="$(check_rate_limit)"
    [ "$result" = "0" ]
'

# --- Test 7: Invalid JSON returns 0 ---
test "invalid JSON returns 0" '
    setup_mock invalid 200 "$INVALID_JSON"
    result="$(check_rate_limit)"
    [ "$result" = "0" ]
'

# --- Test 8: HTTP error returns 0 ---
test "HTTP 403 returns 0" '
    setup_mock http_error 403 ""
    result="$(check_rate_limit)"
    [ "$result" = "0" ]
'

# --- Test 9: Low quota triggers warning ---
test "low quota triggers warning message" '
    setup_mock low_quota 200 "$LOW_QUOTA_SHAPE"
    result="$(check_rate_limit 2>"$PROJECT_ROOT/.mock_stderr")"
    [ "$result" = "10" ] && grep -q "Only 10 API calls remaining" "$PROJECT_ROOT/.mock_stderr"
'

# --- Test 10: Normal quota no warning ---
test "normal quota no warning" '
    setup_mock normal 200 "$OLD_SHAPE"
    result="$(check_rate_limit 2>"$PROJECT_ROOT/.mock_stderr")"
    [ "$result" = "4500" ] && ! grep -q "Only" "$PROJECT_ROOT/.mock_stderr"
'

# Clean up state files
rm -f "$PROJECT_ROOT/.mock_state" "$PROJECT_ROOT/.mock_stderr"

echo ""
echo "=========================================="
echo "Test Results: $tests_passed/$tests_total passed"
echo "=========================================="

if [ "$tests_passed" -eq "$tests_total" ]; then
    echo "ALL TESTS PASS - check_rate_limit() shell function verified"
    exit 0
else
    echo "$((tests_total - tests_passed)) tests failed"
    exit 1
fi
