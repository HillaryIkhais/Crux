#!/usr/bin/env bash
# =============================================================================
# Shared functions for PAT Audit scripts
# Source this file from each step script: source "$(dirname "$0")/lib.sh"
# =============================================================================

API_BASE="https://api.github.com"
GRAPHQL_URL="https://api.github.com/graphql"
API_VERSION="${GITHUB_API_VERSION:-2026-03-10}"

# Project root for relative paths (computed from this script's location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REPORT_DIR="${REPORT_DIR:-./reports}"
mkdir -p "${REPORT_DIR}"

LOOKBACK_DAYS="${LOOKBACK_DAYS:-30}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOOKBACK_DATE="$(date -u -d "${LOOKBACK_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-"${LOOKBACK_DAYS}"d +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------------------
# Rate limit aware REST call — checks remaining quota and waits if needed
# ---------------------------------------------------------------------------
gh_rest() {
  local method="${1}"
  local endpoint="${2}"
  shift 2

  local tmpfile
  tmpfile="$(mktemp)"

  local http_code
  http_code="$(curl -sSL -o "${tmpfile}" -w "%{http_code}" \
    -X "${method}" \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer ${ORG_PAT}" \
    -H "X-GitHub-Api-Version: ${API_VERSION}" \
    -D "${tmpfile}.hdr" \
    "$@" \
    "${API_BASE}${endpoint}" 2>/dev/null || echo "000")"

  # Check for rate limit (403 or 429)
  if [[ "${http_code}" == "403" || "${http_code}" == "429" ]]; then
    local reset_at
    reset_at="$(grep -i '^x-ratelimit-reset:' "${tmpfile}.hdr" 2>/dev/null | tr -d '\r' | awk '{print $2}')"
    if [[ -n "${reset_at}" ]]; then
      local now_epoch
      now_epoch="$(date +%s)"
      local wait_secs=$(( reset_at - now_epoch + 2 ))
      if [[ ${wait_secs} -gt 0 && ${wait_secs} -lt 900 ]]; then
        echo "::warning::Rate limited. Waiting ${wait_secs}s until reset..." >&2
        sleep "${wait_secs}"
        # Retry once
        rm -f "${tmpfile}" "${tmpfile}.hdr"
        curl -fsSL \
          -X "${method}" \
          -H "Accept: application/vnd.github+json" \
          -H "Authorization: Bearer ${ORG_PAT}" \
          -H "X-GitHub-Api-Version: ${API_VERSION}" \
          "$@" \
          "${API_BASE}${endpoint}"
        return
      fi
    fi
    echo "::error::Rate limited on ${endpoint}" >&2
    cat "${tmpfile}"
    rm -f "${tmpfile}" "${tmpfile}.hdr"
    return 1
  fi

  cat "${tmpfile}"
  rm -f "${tmpfile}" "${tmpfile}.hdr"
}

# ---------------------------------------------------------------------------
# Check remaining rate limit and wait if low
# FIXED for GitHub API version 2026-03-10:
# - Prefer resources.core.remaining / resources.core.reset
# - Fall back to rate.remaining / rate.reset only for old API versions
# - Fail safely (return 0) on HTTP errors, invalid JSON, or missing fields
# ---------------------------------------------------------------------------
check_rate_limit() {
  local remaining=0
  local reset_at=""
  local http_code
  local json_data=""
  local parse_error=0

  # Step 1: Make the API call and capture HTTP status code
  http_code="$(curl -sSL -o "$PROJECT_ROOT/.mock_rate_limit.json" -w "%{http_code}" \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer ${ORG_PAT}" \
    -H "X-GitHub-Api-Version: ${API_VERSION}" \
    "${API_BASE}/rate_limit" 2>/dev/null || echo "000")"

  # Step 2: Check for HTTP errors (non-2xx) — fail safely, don't default to 999
  if [[ "${http_code}" != "200" ]]; then
    echo "::warning::rate-limit check failed (HTTP ${http_code}), assuming zero remaining" >&2
    echo "0"
    return 0
  fi

  # Step 3: Read JSON response, fail if empty
  json_data="$(cat "$PROJECT_ROOT/.mock_rate_limit.json" 2>/dev/null)"
  if [[ -z "${json_data}" ]]; then
    echo "::warning::rate-limit response was empty, assuming zero remaining" >&2
    echo "0"
    return 0
  fi

  # Step 4: Validate JSON parses correctly
  if ! echo "${json_data}" | jq '.' >/dev/null 2>&1; then
    echo "::warning::rate-limit response was not valid JSON, assuming zero remaining" >&2
    echo "0"
    return 0
  fi

  # Step 5: Parse remaining quota — try new shape first, fall back to old
  local new_remaining=""
  local old_remaining=""
  new_remaining="$(echo "${json_data}" | jq -r '.resources.core.remaining // empty' 2>/dev/null)"
  old_remaining="$(echo "${json_data}" | jq -r '.rate.remaining // empty' 2>/dev/null)"

  if [[ -n "${new_remaining}" && "${new_remaining}" != "null" ]]; then
    remaining="${new_remaining}"
  elif [[ -n "${old_remaining}" && "${old_remaining}" != "null" ]]; then
    remaining="${old_remaining}"
  else
    echo "::warning::rate-limit response missing remaining field (neither resources.core.remaining nor rate.remaining), assuming zero remaining" >&2
    remaining=0
  fi

  # Step 6: Parse reset time similarly
  local new_reset=""
  local old_reset=""
  new_reset="$(echo "${json_data}" | jq -r '.resources.core.reset // empty' 2>/dev/null)"
  old_reset="$(echo "${json_data}" | jq -r '.rate.reset // empty' 2>/dev/null)"

  if [[ -n "${new_reset}" && "${new_reset}" != "null" ]]; then
    reset_at="${new_reset}"
  elif [[ -n "${old_reset}" && "${old_reset}" != "null" ]]; then
    reset_at="${old_reset}"
  else
    echo "::warning::rate-limit response missing reset field (neither resources.core.reset nor rate.reset), assuming immediate reset" >&2
    reset_at="0"
  fi

  # Step 7: Low quota check — only warn if we have valid data
  if [[ "${remaining}" -lt 50 ]]; then
    local now_epoch
    now_epoch="$(date +%s)"
    local wait_secs=$(( reset_at - now_epoch + 2 ))
    if [[ ${wait_secs} -gt 0 && ${wait_secs} -lt 900 ]]; then
      echo "::warning::Only ${remaining} API calls remaining. Waiting ${wait_secs}s for reset..." >&2
      sleep "${wait_secs}"
    fi
  fi

  echo "${remaining}"
}

# ---------------------------------------------------------------------------
# Authenticated curl for GraphQL
# ---------------------------------------------------------------------------
gh_graphql() {
  local query="${1}"
  curl -fsSL \
    -X POST \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer ${ORG_PAT}" \
    "${GRAPHQL_URL}" \
    -d "${query}"
}

# ---------------------------------------------------------------------------
# Paginated REST fetch with rate limit awareness
# ---------------------------------------------------------------------------
gh_rest_paginated() {
  local endpoint="${1}"
  local per_page="${2:-100}"
  local max_pages="${3:-20}"
  local results="[]"
  local page=1

  while [[ $page -le $max_pages ]]; do
    local separator="?"
    if [[ "${endpoint}" == *"?"* ]]; then
      separator="&"
    fi
    local response
    response="$(gh_rest GET "${endpoint}${separator}per_page=${per_page}&page=${page}" 2>/dev/null || echo "[]")"

    local count
    count="$(echo "${response}" | jq 'if type == "array" then length else 0 end' 2>/dev/null || echo "0")"

    if [[ "${count}" -eq 0 ]]; then
      break
    fi

    results="$(echo "${results}" "${response}" | jq -s '.[0] + .[1]')"
    page=$((page + 1))

    if [[ "${count}" -lt "${per_page}" ]]; then
      break
    fi

    # Brief pause between pages to avoid rate limiting
    sleep 0.5
  done

  echo "${results}"
}

# ---------------------------------------------------------------------------
# Validate PAT and org access (cached via file to avoid repeat API calls)
# ---------------------------------------------------------------------------
validate_auth() {
  if [[ -z "${ORG_PAT:-}" ]]; then
    echo "::error::ORG_PAT secret is not set."
    exit 1
  fi
  if [[ -z "${ORG_NAME:-}" ]]; then
    echo "::error::ORG_NAME is not set."
    exit 1
  fi

  # Use cached auth if available (avoids burning 2 API calls per script)
  if [[ -f "${REPORT_DIR}/_auth_cache.json" ]]; then
    AUTH_USER="$(jq -r '.user' "${REPORT_DIR}/_auth_cache.json")"
    ORG_ID="$(jq -r '.org_id' "${REPORT_DIR}/_auth_cache.json")"
    echo "   Authenticated as: ${AUTH_USER} (cached)"
    echo "   Organization: ${ORG_NAME} (ID: ${ORG_ID})"
    return 0
  fi

  AUTH_CHECK="$(gh_rest GET "/user" 2>/dev/null || echo "{}")"
  AUTH_USER="$(echo "${AUTH_CHECK}" | jq -r '.login // "UNKNOWN"')"
  if [[ "${AUTH_USER}" == "UNKNOWN" ]]; then
    echo "::error::Failed to authenticate with the provided PAT."
    exit 1
  fi
  echo "   Authenticated as: ${AUTH_USER}"

  ORG_INFO="$(gh_rest GET "/orgs/${ORG_NAME}" 2>/dev/null || echo "{}")"
  ORG_ID="$(echo "${ORG_INFO}" | jq -r '.id // "UNKNOWN"')"
  if [[ "${ORG_ID}" == "UNKNOWN" ]]; then
    echo "::error::Cannot access organization '${ORG_NAME}'."
    exit 1
  fi
  echo "   Organization: ${ORG_NAME} (ID: ${ORG_ID})"

  # Cache for subsequent scripts
  echo "{\"user\": \"${AUTH_USER}\", \"org_id\": \"${ORG_ID}\"}" > "${REPORT_DIR}/_auth_cache.json"
}
