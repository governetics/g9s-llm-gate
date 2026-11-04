#!/usr/bin/env bash
# Real-environment smoke test for the llm-gate proxy (remote HTTPS via
# g9s-edge, or a local stack). Exercises the operator surface: auth
# enforcement, model listing under a scoped virtual key, non-streaming,
# SSE streaming and tool use -- the same /v1/messages path Claude Code
# relies on.
#
# Env:
#   BASE_URL    gateway base URL without a trailing slash
#               (default: https://llm-gate.lab.governetics.ru)
#   SMOKE_KEY   virtual key, sent as "Authorization: Bearer ...";
#               REQUIRED; its value is never printed by this script
#   MODEL       public alias under test (default: opus)
#   TOOL_MODEL  public alias for the tool-use step (default: fable;
#               the two defaults cover both providers in one run)
#               Model aliases are interpolated into a JSON body and a grep
#               pattern: use plain identifiers (letters, digits, -, _, [1m]),
#               not values with quotes or backslashes.
#
# Every step prints "PASS <name>" or "FAIL <name> -- <reason>"; on failure
# a short (<=200 chars) one-line response fragment is included. Full
# response bodies are never dumped.
#
# Exit codes: 0 all steps passed; 1 at least one step failed;
# 2 bad invocation (e.g. SMOKE_KEY not set). No "set -x" here on purpose:
# the key travels in request headers.

set -uo pipefail

if [[ -z "${SMOKE_KEY:-}" ]]; then
    echo "ERROR: SMOKE_KEY is not set (the virtual key for the gateway)." >&2
    exit 2
fi

BASE_URL="${BASE_URL:-https://llm-gate.lab.governetics.ru}"
BASE_URL="${BASE_URL%/}"
MODEL="${MODEL:-opus}"
TOOL_MODEL="${TOOL_MODEL:-fable}"
MAX_TIME=60
FAILED=0

SMOKE_TMP="$(mktemp -d)"
trap 'rm -rf "$SMOKE_TMP"' EXIT

# request <url> [extra curl args...] -> sets $CODE (HTTP status), response
# body in $SMOKE_TMP/body, curl diagnostics in $SMOKE_TMP/err. A network
# level failure yields CODE=000 so the step reports FAIL, not a crash.
request() {
    local url="$1"; shift
    CODE="$(curl -sS -o "$SMOKE_TMP/body" -w '%{http_code}' \
        --max-time "$MAX_TIME" "$@" "$url" 2>"$SMOKE_TMP/err")" || CODE=000
}

# report PASS|FAIL <name> [reason]
report() {
    local status="$1" name="$2" reason="${3:-}"
    if [[ "$status" == PASS ]]; then
        echo "PASS $name"
    else
        echo "FAIL $name -- $reason"
        FAILED=$((FAILED + 1))
    fi
}

# Short one-line fragment of the last response body (curl error text when
# there is no body), for FAIL lines only.
fragment() {
    local frag
    frag="$(head -c 200 "$SMOKE_TMP/body" 2>/dev/null | tr '\n' ' ')"
    if [[ -z "$frag" && -s "$SMOKE_TMP/err" ]]; then
        frag="$(head -c 200 "$SMOKE_TMP/err" | tr '\n' ' ')"
    fi
    printf '%s' "$frag"
}

echo "smoke against $BASE_URL (model: $MODEL, tool model: $TOOL_MODEL)"

# 1. auth-negative: without a key the gateway must refuse (401/403).
request "$BASE_URL/v1/models"
if [[ "$CODE" == 401 || "$CODE" == 403 ]]; then
    report PASS auth-negative
else
    report FAIL auth-negative "expected 401/403 without a key, got $CODE; $(fragment)"
fi

# 2. models: with the key -> 200 and the tested alias must be listed
# (a scoped virtual key lists only its allowed models, so a missing alias
# means a scope problem, not just a typo).
request "$BASE_URL/v1/models" -H "authorization: Bearer $SMOKE_KEY"
if [[ "$CODE" == 200 ]] && grep -Fq "\"${MODEL}\"" "$SMOKE_TMP/body"; then
    report PASS models
else
    report FAIL models "expected 200 with alias '$MODEL' listed, got $CODE; $(fragment)"
fi

# 3. messages non-stream: minimal Anthropic-protocol round trip.
request "$BASE_URL/v1/messages" \
    -H "authorization: Bearer $SMOKE_KEY" \
    -H "content-type: application/json" \
    --data "{\"model\":\"$MODEL\",\"max_tokens\":48,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: pong\"}]}"
if [[ "$CODE" == 200 ]]; then
    report PASS messages
else
    report FAIL messages "expected 200 for non-stream /v1/messages, got $CODE; $(fragment)"
fi

# 4. messages stream: 200 is not enough, the body must be an SSE stream.
request "$BASE_URL/v1/messages" \
    -H "authorization: Bearer $SMOKE_KEY" \
    -H "content-type: application/json" \
    --data "{\"model\":\"$MODEL\",\"max_tokens\":48,\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: pong\"}]}"
if [[ "$CODE" == 200 ]] && grep -aq '^event:' "$SMOKE_TMP/body"; then
    report PASS sse
else
    report FAIL sse "expected 200 with SSE 'event:' lines, got $CODE; $(fragment)"
fi

# 5. tool use on TOOL_MODEL: PASS when the response contains tool_use
# (stop_reason "tool_use" and/or a tool_use content block -- either
# satisfies the check).
request "$BASE_URL/v1/messages" \
    -H "authorization: Bearer $SMOKE_KEY" \
    -H "content-type: application/json" \
    --data "{\"model\":\"$TOOL_MODEL\",\"max_tokens\":128,\"tools\":[{\"name\":\"get_weather\",\"description\":\"Get the current weather for a city\",\"input_schema\":{\"type\":\"object\",\"properties\":{\"city\":{\"type\":\"string\"}},\"required\":[\"city\"]}}],\"messages\":[{\"role\":\"user\",\"content\":\"What is the weather in Paris? Use the get_weather tool.\"}]}"
if [[ "$CODE" == 200 ]] && grep -Fq "tool_use" "$SMOKE_TMP/body"; then
    report PASS tool-use
else
    report FAIL tool-use "expected 200 with tool_use on '$TOOL_MODEL', got $CODE; $(fragment)"
fi

TOTAL=5
PASSED=$((TOTAL - FAILED))
echo "smoke: $PASSED/$TOTAL steps passed"
if [[ "$FAILED" -gt 0 ]]; then
    exit 1
fi
exit 0
