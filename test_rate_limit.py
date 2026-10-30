"""CRUX: Faithful reproduction of GitHub API 2026-03-10 rate-limit change break."""

import json
import pytest


# The OLD parser that reads rate from JSON body (pre-2026-03-10 code)
def old_rate_limit_parser(response):
    """Parser from before the API change - reads rate.remaining from JSON."""
    data = response.json()
    rate_data = data['rate']  # Will KeyError: 'rate' key removed
    remaining = rate_data['remaining']  # Will KeyError if missing
    return remaining


# The NEW parser that reads from resources.core in JSON body (post-2026-03-10 compatible)
def new_rate_limit_parser(response):
    """Parser compatible with API 2026-03-10 - reads resources.core from JSON body.
    Falls back to rate.remaining for old API versions. Fails safe (returns 0) on missing data.
    """
    data = response.json()
    # Try new shape first
    resources = data.get('resources', {})
    core = resources.get('core', {})
    remaining = core.get('remaining')
    if remaining is not None:
        return int(remaining)
    # Fall back to old shape
    rate = data.get('rate', {})
    remaining = rate.get('remaining')
    if remaining is not None:
        return int(remaining)
    # Fail safe: no silent 999 default
    return 0


# Mock response simulating GitHub API 2026-03-10 behavior
# The 'rate' key is intentionally removed from the JSON body.
# Rate limit info is now provided via resources.core in the JSON body.
MOCK_NEW_API = {
    "status_code": 200,
    "json_data": {
        "resources": {
            "core": {
                "limit": 5000,
                "remaining": 4300,
                "used": 700,
                "reset": 1000
            }
        }
    },
    "headers": {
        "X-RateLimit-Limit": "5000",
        "X-RateLimit-Remaining": "4300",
        "X-RateLimit-Reset": "1000"
    }
}

# Mock response simulating pre-2026-03-10 API behavior
# The 'rate' key exists in the JSON body.
MOCK_OLD_API = {
    "status_code": 200,
    "json_data": {
        "rate": {"limit": 5000, "remaining": 4500, "used": 500, "reset": 1000},
        "resources": {
            "core": {"limit": 5000, "remaining": 4500, "used": 500, "reset": 1000}
        }
    },
    "headers": {
        "X-RateLimit-Limit": "5000",
        "X-RateLimit-Remaining": "4500",
        "X-RateLimit-Reset": "1000"
    }
}


class MockResponse:
    """Minimal mock response object for testing."""
    def __init__(self, data, headers):
        self._data = data
        self._headers = headers

    def json(self):
        return self._data

    @property
    def headers(self):
        return self._headers


class TestRateLimitChange:
    """Tests demonstrating the GitHub API 2026-03-10 break and fix."""

    def test_old_parser_with_old_api_works(self):
        """Old parser works with old API (baseline)."""
        response = MockResponse(MOCK_OLD_API["json_data"], MOCK_OLD_API["headers"])
        result = old_rate_limit_parser(response)
        assert result == 4500

    def test_old_parser_with_new_api_fails(self):
        """Old parser FAILS with new API - this is the break."""
        response = MockResponse(MOCK_NEW_API["json_data"], MOCK_NEW_API["headers"])
        with pytest.raises(KeyError):
            old_rate_limit_parser(response)

    def test_new_parser_with_new_api_works(self):
        """New parser works with new API (the fix)."""
        response = MockResponse(MOCK_NEW_API["json_data"], MOCK_NEW_API["headers"])
        result = new_rate_limit_parser(response)
        assert result == 4300

    def test_new_parser_with_old_api_works(self):
        """New parser also works with old API (backward compatible)."""
        response = MockResponse(MOCK_OLD_API["json_data"], MOCK_OLD_API["headers"])
        result = new_rate_limit_parser(response)
        assert result == 4500
