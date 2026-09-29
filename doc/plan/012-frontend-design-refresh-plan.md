# HeavyChat Frontend Design Refresh Plan

- **Created:** 2026-09-29T13:12:46+00:00
- **Study:** [`doc/study/012-frontend-design-refresh-study.md`](../study/012-frontend-design-refresh-study.md)
- **Status:** Execution authorized by the user's request.
- **Scope:** Refresh all app/login template styling and shared CSS without changing application interactions.

## Checklist

- [x] Establish slate-neutral background/panel/border tokens, readable primary/body/muted text levels, and emerald/indigo accents.
- [x] Improve shared shell, sidebar/navigation/session list, balance pill, home/profile/model modal, and login page spacing, typography, surfaces, and focus states.
- [x] Update conversation/message styling for clear right-aligned user bubbles, centered readable assistant width, markdown/code rhythm, scrollable feed, and bottom-pinned composer.
- [x] Preserve Tailwind/CDN dependencies, HTMX targets, CSRF inputs, JS class/data hooks, Markdown sanitizer/highlighter behavior, and streaming auto-scroll.
- [x] Run `.venv/bin/python manage.py check` and `.venv/bin/python -m pytest`; confirm 34 tests pass.
- [x] Review the frontend diff and commit on `main` as `style: polish UI design, typography contrast, and chat layout`.

## Verification

- There are no browser screenshot tests; validate responsive styling through the existing CSS breakpoints and ensure all existing template/streaming tests remain green.
- No changes to models, migrations, provider contracts, or credentials are in scope.
