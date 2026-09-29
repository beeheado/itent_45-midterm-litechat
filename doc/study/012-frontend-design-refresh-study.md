# HeavyChat Frontend Design Refresh Study

- **Created:** 2026-09-29T13:12:46+00:00
- **Status:** Study complete; the user requested the visual redesign and commit.
- **Scope:** Refresh the shared slate theme and all chat/login template surfaces while preserving streaming, HTMX, Markdown sanitization/highlighting, and existing interaction hooks.

## Verified Facts

- The branch is `main` and the worktree was clean at commit `6068fc5` before this task.
- Tailwind's CDN script, marked.js, highlight.js, DOMPurify, HTMX, and the GitHub Dark highlight stylesheet are already loaded in the shared base template; the login template also loads Tailwind and local CSS.
- `chat/static/chat/css/app.css` currently defines the whole interface in custom component selectors. It uses very dark navy/green panels, many small 8-13px text styles, muted metadata, and a constrained conversation layout. Shared selectors cover the base shell, home, conversation, profile, model modal, and login view.
- Templates include shared base/login layouts plus home, session, profile, model selector, message, session list, balance badge, memory list/toggle, and prompt-saved partials. `app.js` relies on classes/data attributes for streamed messages, auto-scroll, HTMX swaps, model layout switching, and markdown rendering.
- The existing suite contains 34 tests and asserts functionality/markup but does not include browser screenshot or visual-regression coverage.

## Tradeoffs and Risks

- Retain the established component selectors and interaction/data attributes; modernize their design tokens and improve the few structures needed for legibility and message width instead of replacing working Django/HTMX/streaming behavior.
- Use a cohesive slate-neutral surface palette, readable type scale, emerald balance accents, and indigo user-message treatment. Use Tailwind utilities in templates where they add clear utility-level behavior while keeping `app.css` authoritative for the existing component system.
- Keep the composer in the conversation flex column with a sticky bottom wrapper and a scrollable message feed. Preserve the JS-driven append/scroll and SSE classes exactly.
- External CDN availability remains outside local test coverage. Do not change CDN versions or sanitization/streaming order during the visual-only refresh.
- Production visual confidence is limited without browser/device screenshot tooling; verify responsive rules and run the full Django suite.

## Assumptions and Open Questions

- “Across all templates” includes shared app chrome, home, session, profile, modal/partials, and the standalone login page.
- The existing dark theme and mint/emerald brand identity should remain recognizable while reducing near-black surfaces and improving contrast/readability.
- No data model, view, route, provider, or frontend interaction behavior should change.

## Decision

Proceed with a focused design-system refresh in `app.css` and small template markup adjustments across all user-facing templates. Retain CDN dependencies, HTMX targets, CSRF fields, stream URLs, and data attributes. Verify via Django check and the 34-test suite, then commit on `main` with the requested style commit message.
