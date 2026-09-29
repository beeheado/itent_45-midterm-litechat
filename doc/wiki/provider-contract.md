# LiteChat Provider Contract

## Status

Phase 1 provider capture is complete using the live fixture supplied in `tests/fixtures/provider_stream.sse`. The fixture bytes were inspected locally and not modified. The endpoint, model, and HTTP 200 status came with the user's capture report; response headers and exact capture time were not supplied.

## Routing and Model

- **Provider base URL:** `https://proxy.litechat.ai/openai/v1`
- **Chat Completions endpoint:** `https://proxy.litechat.ai/openai/v1/chat/completions`
- **Model discovery:** `/models` is unmapped on this gateway. Requests must use the provider-prefixed route and a known model instead of model discovery.
- **Observed model:** `gpt-5.6-luna` (also present in the captured completion chunks).
- **Reported response status:** HTTP 200, as supplied with the live fixture.
- **Response headers:** Not included with the supplied fixture; `sanitized_headers` is empty rather than inferred.

The previous request to `https://proxy.litechat.ai/v1/models` returned HTTP 404. The route resolution is the added `/openai` provider prefix, not evidence that the key was invalid.

## Stream Shape

The fixture contains 51 JSON `data:` events, followed by `data: [DONE]` and the terminating blank line. Each completion event uses an OpenAI-style `choices` array and `choices[0].delta`.

- Deltas contain `reasoning_content` as well as `content`. In this fixture, 47 deltas have non-null `reasoning_content` (one is an empty string), and 3 have non-null `content` (one is an empty string).
- Reasoning and user-facing content are separate fields. Do not concatenate `reasoning_content` into `content` or render it as ordinary assistant output. Keep its handling separate pending an explicit product policy.
- The last choice-bearing chunk has `finish_reason: "stop"`.
- A following usage-only chunk has `choices: []` and `usage` with `prompt_tokens: 208`, `completion_tokens: 49`, and `total_tokens: 257`. Its `completion_tokens_details.reasoning_tokens` is `46`; it also reports prompt cache hit/miss fields.
- The stream then terminates with the `data: [DONE]` sentinel.

The ordering matters: the client must continue reading after `finish_reason` to receive the separate usage chunk, and only then process `[DONE]`. Do not assume every event has text in `delta.content` or even a non-empty `choices` array.

## Fixture Provenance

- Raw fixture: [`tests/fixtures/provider_stream.sse`](../../tests/fixtures/provider_stream.sse)
- Metadata: [`tests/fixtures/provider_stream_meta.json`](../../tests/fixtures/provider_stream_meta.json)
- Raw byte length: 15,426
- SHA-256: `aa2219921ad676ac448eadd2ebfa86675d040ee22b119156e25e479ae7d6734b`
- Models, usage fields, finish reason, delta-field counts, and termination sentinel were parsed from the fixture. Capture timestamp and response headers were unavailable from the supplied artifact, so neither is presented as observed.

## Capture Tool

[`scripts/capture_proxy.py`](../../scripts/capture_proxy.py) reads `LITECHAT_API_KEY` from the repository `.env` and posts directly to the provider-prefixed Chat Completions endpoint. Its default model is `gpt-5.6-luna`; it no longer calls `/models`. It stores response bytes unchanged and writes allowlisted response headers and stream observations to the metadata file. Redirects are rejected so the bearer token is not forwarded to another host.

## Parser Contract

The stream consumer must:

- Append `delta.content` to the user-visible assistant response when it is a string.
- Handle `delta.reasoning_content` independently; do not expose it as user-visible content by default.
- Continue after a `finish_reason` chunk and consume the subsequent usage-only chunk.
- Read the aggregate prompt/completion token counts from the final usage object and recognize `[DONE]` as stream termination.
