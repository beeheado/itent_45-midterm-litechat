# LiteChat Provider Contract

## Status

Provider contract capture is **blocked**. No model list or streaming completion has been observed, so this document makes no claims about LiteChat's completion payload, delta schema, final usage object, or `[DONE]` behavior.

## Capture Attempt

- **Captured at:** 2026-09-29T05:15:00Z
- **Method:** `python3 scripts/capture_proxy.py`
- **Credential handling:** The script read `LITECHAT_API_KEY` from the repository `.env` and sent it as a bearer credential. The key value was not printed or written to artifacts. `.env` is excluded by `.gitignore`. The 404 does not establish whether the credential itself is valid.
- **Capture client:** Python 3.12.3, standard-library `urllib.request`
- **Request:** `GET https://proxy.litechat.ai/v1/models` with a bearer authorization header
- **Result:** HTTP 404, `content-type: text/plain; charset=utf-8`
- **Request ID:** `req_u34MlSunYED7xBkIZeiPwWCuTt47TEY6MHVKHrtjeW4`
- **Models returned:** None
- **Completion request:** Not sent because no active model could be discovered.

The sanitized response facts are recorded in [`tests/fixtures/provider_stream_meta.json`](../../tests/fixtures/provider_stream_meta.json). This metadata is an error record, not a successful provider capture. `tests/fixtures/provider_stream.sse` was intentionally not created; no raw SSE bytes were received, and no synthetic stream was substituted.

## What Is and Is Not Verified

This attempt verifies only that the supplied base URL's `/models` route returned HTTP 404 to this request. It does not establish that the API key is invalid, that all LiteChat API routes are unavailable, or that `/chat/completions` lacks streaming support. The prior plain GET to the base URL also returned 404 and is not a substitute for a successful API request.

There is no provider evidence yet for:

- Available model IDs, capabilities, or model-list pagination.
- Chat completion request options accepted by the proxy.
- SSE event framing, role/content/tool deltas, finish reasons, or error events.
- A final usage event or `prompt_tokens`/`completion_tokens` fields.
- The `[DONE]` sentinel or response headers on a successful stream.

## Capture Tool

[`scripts/capture_proxy.py`](../../scripts/capture_proxy.py) loads the key from `.env`, requests the model list, chooses a returned active model (or validates `--model`), and is prepared to write raw SSE bytes and sanitized response metadata. Redirects are rejected so the bearer token is not forwarded to another host. Failed HTTP responses record only the endpoint, method, status, timestamp, and allowlisted headers; response bodies and credentials are not persisted.

## Resume Gate

Confirm the correct API route/configuration with the provider or account owner, then rerun the capture script. Once model discovery succeeds, capture a minimal synthetic streaming completion to `tests/fixtures/provider_stream.sse` and verify its final usage and termination behavior before finalizing any parser contract. Preserve the raw response unchanged and keep provenance metadata free of credentials and personal data.
