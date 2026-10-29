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

# The NEW parser that reads from headers (post-2026-03-10 compatible)
def new_rate_limit_parser(response):
    """Parser compatible with API 2026-03-10 - reads from headers."""
    remaining = response.headers.get('RateLimit-Remaining', '0')
    return int(remaining) if remaining else 0


# Mock response simulating GitHub API 2026-03-10 behavior
# The 'rate' key is intentionally removed from the JSON body.
# Rate limit info is provided via HTTP headers only.
MOCK_NEW_API = {
    "status_code": 200,
    "json_data": {},  # No 'rate' key - this is the break!
    "headers": {
        "RateLimit-Limit": "5000",
        "RateLimit-Remaining": "4500",
        "RateLimit-Reset": "1000"
    }
}

# Mock response simulating pre-2026-03-10 API behavior
# The 'rate' key exists in the JSON body.
MOCK_OLD_API = {
    "status_code": 200,
    "json_data": {
        "rate": {"limit": 5000, "remaining": 4500, "used": 500}
    },
    "headers": {
        "RateLimit-Limit": "5000",
        "RateLimit-Remaining": "4500",
        "RateLimit-Reset": "1000"
    }
}


class TestRateLimitChange:
    """Tests demonstrating the GitHub API 2026-03-10 break and fix."""

    def test_old_parser_with_old_api_works(self):
        """Old parser works with old API (baseline)."""
        class MockResponse:
            def __init__(self, data, headers):
                self._data = data
                self._headers = headers
            
            def json(self):
                return self._data
            
            @property
            def headers(self):
                return self._headers
        
        response = MockResponse(MOCK_OLD_API["json_data"], MOCK_OLD_API["headers"])
        result = old_rate_limit_parser(response)
        assert result == 4500

    def test_old_parser_with_new_api_fails(self):
        """Old parser FAILS with new API - this is the break."""
        class MockResponse:
            def __init__(self, data, headers):
                self._data = data
                self._headers = headers
            
            def json(self):
                return self._data
            
            @property
            def headers(self):
                return self._headers
        
        response = MockResponse(MOCK_NEW_API["json_data"], MOCK_NEW_API["headers"])
        with pytest.raises(KeyError):
            old_rate_limit_parser(response)

    def test_new_parser_with_new_api_works(self):
        """New parser works with new API (the fix)."""
        class MockResponse:
            def __init__(self, data, headers):
                self._data = data
                self._headers = headers
            
            def json(self):
                return self._data
            
            @property
            def headers(self):
                return self._headers
        
        response = MockResponse(MOCK_NEW_API["json_data"], MOCK_NEW_API["headers"])
        result = new_rate_limit_parser(response)
        assert result == 4500

    def test_new_parser_with_old_api_works(self):
        """New parser also works with old API (backward compatible)."""
        class MockResponse:
            def __init__(self, data, headers):
                self._data = data
                self._headers = headers
            
            def json(self):
                return self._data
            
            @property
            def headers(self):
                return self._headers
        
        response = MockResponse(MOCK_OLD_API["json_data"], MOCK_OLD_API["headers"])
        result = new_rate_limit_parser(response)
        assert result == 4500
