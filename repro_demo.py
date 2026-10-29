"""CRUX: Reproduction of GitHub API 2026-03-10 rate-limit change break.

Demonstrates the before/after behavior using inline JSON fixtures (no external
dependencies required). Mirrors the real jq expressions used in
scripts/lib.sh::check_rate_limit().
"""

import json
import subprocess
import sys


def jq(expr, data):
    """Run a jq expression against JSON data, return stripped output."""
    input_str = json.dumps(data) if isinstance(data, dict) else data
    result = subprocess.run(
        ["jq", "-r", expr],
        input=input_str,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


# Fixtures: old and new API response shapes
OLD_SHAPE = {
    "rate": {
        "limit": 5000,
        "remaining": 4500,
        "used": 500,
        "reset": 1000
    },
    "resources": {
        "core": {
            "limit": 5000,
            "remaining": 4500,
            "used": 500
        }
    }
}

NEW_SHAPE = {
    "resources": {
        "core": {
            "limit": 5000,
            "remaining": 4300,
            "used": 700,
            "reset": 1000
        }
    }
}

# jq expressions (same as used in scripts/lib.sh::check_rate_limit)
OLD_JQ_REMAINING = ".rate.remaining // 999"
NEW_JQ_REMAINING = ".resources.core.remaining // .rate.remaining // empty"
NEW_JQ_RESET = ".resources.core.reset // .rate.reset // empty"


def main():
    print("CRUX: GitHub API 2026-03-10 Rate Limit Change Demo")
    print("=" * 70)
    print()
    print("Official change: 'rate' property removed from GET /rate_limit")
    print("Response body now carries resources.core.remaining / resources.core.reset")
    print()

    # --- Demonstration 1: Old parser breaks on new shape ---
    print("DEMONSTRATION 1: Old parser fails on new API response")
    print("-" * 70)

    old_result = jq(OLD_JQ_REMAINING, NEW_SHAPE)
    print(f"Old jq `.rate.remaining // 999` on new shape:")
    print(f"  Result: {old_result}  <-- silently falls back to 999!")
    print(f"  Effect: low-quota guard `[ remaining -lt 50 ]` never fires")
    print()

    # --- Demonstration 2: Fixed parser works on both shapes ---
    print("DEMONSTRATION 2: Fixed parser works on both shapes")
    print("-" * 70)

    new_result_old = jq(NEW_JQ_REMAINING, OLD_SHAPE)
    new_result_new = jq(NEW_JQ_REMAINING, NEW_SHAPE)
    print(f"Fixed jq `.resources.core.remaining // .rate.remaining // empty`:")
    print(f"  On old shape:  {new_result_old}")
    print(f"  On new shape:  {new_result_new}")
    print()

    # --- Demonstration 3: Fail-safe on empty/invalid data ---
    print("DEMONSTRATION 3: Fail-safe behavior on missing/invalid data")
    print("-" * 70)

    empty_result = jq(NEW_JQ_REMAINING, {})
    missing_result = jq(NEW_JQ_REMAINING, {"other": "data"})
    print(f"Empty JSON `{{}}`: remaining = '{empty_result}'  (fail-safe, not 999)")
    print(f"Missing data: remaining = '{missing_result}'  (fail-safe, not 999)")
    print()

    # --- Demonstration 4: Low quota triggers warning ---
    print("DEMONSTRATION 4: Low quota is detected")
    print("-" * 70)

    low_quota = {"resources": {"core": {"remaining": 10, "reset": 9999999999}}}
    low_result = jq(NEW_JQ_REMAINING, low_quota)
    print(f"Low quota shape (remaining=10): remaining = {low_result}")
    print(f"  Guard: [ {low_result} -lt 50 ] → true → warning triggered")
    print()

    print("CONCLUSION:")
    print("  The `rate` property removal breaks code reading `.rate.remaining`")
    print("  from the JSON body. The fix migrates to `resources.core.remaining`")
    print("  with `.rate.remaining` fallback and `// empty` fail-safe.")
    print()


if __name__ == "__main__":
    main()
