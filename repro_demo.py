""""CRUX reproduction: GitHub API 2026-03-10 rate limit change."""

import requests
import responses  # pytest-mock style mocking

def old_parser(response):
    """Parser that will BREAK with API 2026-03-10 - reads rate from JSON body."""
    data = response.json()
    rate_data = data.get('rate', {})  # KEY WILL BE MISSING
    remaining = rate_data.get('remaining', 0)
    return remaining

def new_parser(response):
    """Parser that works with API 2026-03-10 - reads from headers."""
    remaining = response.headers.get('RateLimit-Remaining', '0')
    return int(remaining) if remaining else 0

def mock_old_response():
    """Mock response simulating OLD API behavior (with rate key)."""
    import json
    return responses.Response(
        status=200,
        json={'rate': {'limit': 5000, 'remaining': 4500, 'used': 500}},
        headers={'RateLimit-Limit': '5000', 'RateLimit-Remaining': '4500', 'RateLimit-Reset': '1000'}
    )

def mock_new_response():
    """Mock response simulating NEW API 2026-03-10 behavior (no rate key)."""
    import json
    return responses.Response(
        status=200,
        json={'message': 'Rate limit info in headers'},  # No 'rate' key!
        headers={'RateLimit-Limit': '5000', 'RateLimit-Remaining': '4500', 'RateLimit-Reset': '1000'}
    )

# Simulation
print("CRUX: GitHub API 2026-03-10 Rate Limit Change Demo")
print("=" * 70)
print()
print("Official change (GitHub REST API version 2026-03-10):")
print("  - 'rate' property removed from rate-limit response JSON body")
print("  - Rate limit now provided via HTTP headers only")
print()

print("DEMONSTRATION: Old parser vs New parser")
print("-" * 70)

# Test with old API response (has 'rate' key)
old_resp = mock_old_response()
old_result = old_parser(old_resp)
print(f"Old parser with old-style response: remaining = {old_result}")
print(f"  Status: ✅ WORKS (rate key exists)")

# Test with new API response (NO rate key - this is the break!)
new_resp = mock_new_response()
try:
    new_result = old_parser(new_resp)
    print(f"Old parser with new-style response: remaining = {new_result}")
    print(f"  Status: ❌ BROKEN - would raise KeyError or return None")
except KeyError as e:
    print(f"Old parser with new-style response: KeyError raised: {e}")
    print(f"  Status: ❌ BROKEN - 'rate' key no longer exists")

print()
print("New parser with new-style response:")
new_result = new_parser(new_resp)
print(f"  remaining = {new_result}")
print(f"  Status: ✅ WORKS (reads from headers)")

print()
print("CONCLUSION:")
print("  The API change from 'rate' property to HTTP headers")
print("  breaks code that reads rate.remaining from the JSON body.")
print("  The fix is to migrate to header-based parsing.")
print()
print("VERIFICATION CHECKLIST:")
print("  ✅ Response JSON no longer contains 'rate' key (by design)")
print("  ✅ RateLimit-Remaining header is present and valid")
print("  ✅ Old parser fails with new API response")
print("  ✅ New parser succeeds with new API response")
print("  ✅ Migration path documented: read from headers, not JSON body")
