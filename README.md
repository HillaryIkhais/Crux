# CRUX

**Find the break. Prove the cause. Verify the fix.**

CRUX is an evidence-first API migration repair tool. It investigates upstream
API changes, traces their impact on real downstream code, reproduces the
incompatibility, verifies a repair, and publishes a traceable case report.

## The Case Study: GitHub REST API 2026-03-10

GitHub's REST API version `2026-03-10` removed the `rate` property from the
`GET /rate_limit` response. Rate limit information is now provided via
`resources.core.remaining` and `resources.core.reset` instead.

This change silently breaks downstream consumers that read
`rate_limit_json['rate']['remaining']` — they fall back to `999` (showing
"plenty of quota") even when quota is low, disabling low-quota warnings and
waiting behavior.

CRUX demonstrates this with a real downstream consumer:
**`jackgkafaty/GitHub_PAT_AUDIT`**, whose `scripts/lib.sh`
`check_rate_limit()` function reads `.rate.remaining // 999` and
`.rate.reset // 0`.

## Project Structure

```
crux/
├── README.md                 # This file
├── CASE_STUDY.md             # Full migration case study with evidence
├── changes.json              # Documented API changes + test results
├── upstream_facts.json       # Verified upstream facts from official sources
├── repro_demo.py             # Reproduction demonstration script
├── test_rate_limit.py        # pytest tests (4 tests) - parser-level break/fix
├── test_safe_parsing.py      # jq expression tests (9 tests) - fail-safe behavior
├── tests/check_rate_limit.sh # Shell function tests (10 tests) - mocked curl
├── scripts/lib.sh            # Fixed check_rate_limit() implementation
└── fixtures/                 # Test fixtures (old/new/missing/invalid JSON shapes)
    ├── old_rate_limit.json
    ├── new_rate_limit.json
    ├── missing_core.json
    ├── missing_remaining.json
    ├── missing_reset.json
    ├── empty.json
    ├── low_quota.json
    └── invalid_json.txt
```

## Run the Tests

### Python pytest suite (parser-level break/fix)
```bash
python3 -m pytest test_rate_limit.py -v
# Expected: 4 passed
```

### jq-expression tests (fail-safe parsing)
```bash
python3 test_safe_parsing.py
# Expected: 9/9 passed
```

### Shell function tests (actual check_rate_limit() with mocked curl)
```bash
bash tests/check_rate_limit.sh
# Expected: 10/10 passed
```

### Run all suites
```bash
python3 -m pytest test_rate_limit.py -v && \
python3 test_safe_parsing.py && \
bash tests/check_rate_limit.sh
# Expected: All suites pass
```

## The Fix

The `check_rate_limit()` function in `scripts/lib.sh` was repaired to:

1. **Prefer `resources.core.remaining` / `resources.core.reset`** (API 2026-03-10 shape)
2. **Fall back to `rate.remaining` / `rate.reset`** (pre-2026-03-10 shape) for backward compatibility
3. **Use `// empty` (fail-safe)** instead of `// 999` / `// 0` — missing fields return empty → 0, never silently default to abundant quota
4. **Validate HTTP status code** — non-200 responses return 0 with a warning
5. **Validate JSON** — invalid responses return 0 with a warning
6. **Check `remaining < 50`** — only triggers low-quota warning and waiting when valid data exists

## Key Test Results

| Suite | Tests | Passed | Failed |
|-------|-------|--------|--------|
| `test_rate_limit.py` | 4 | 4 | 0 |
| `test_safe_parsing.py` | 9 | 9 | 0 |
| Shell function tests | 10 | 10 | 0 |
| **Total** | **23** | **23** | **0** |

## Known Limitations

- Tests use mocked JSON fixtures derived from GitHub's official documentation (no live API calls, no authentication/PAT)
- The downstream repository (`jackgkafaty/GitHub_PAT_AUDIT`) was cloned and inspected; the fix is the recommended pattern, not committed to that repository
- This is confirmed code behavior analysis based on the actual `scripts/lib.sh` source, not a live production incident

## Evidence Chain

1. **Upstream change**: GitHub REST API `2026-03-10` removed `rate` from rate-limit response
2. **Downstream consumer**: `jackgkafaty/GitHub_PAT_AUDIT/scripts/lib.sh` `check_rate_limit()`
3. **Failure reproduced**: Old `jq '.rate.remaining // 999'` returns `999` on new API response
4. **Repair verified**: New jq chain `.resources.core.remaining // .rate.remaining // empty` returns correct values
5. **Tests establish**: 23/23 passing across all suites
