# Operating Protocols

## Workflow Loop

For every new outcome, follow this sequence without skipping or reordering steps:

**Study => Plan => Execute plan => Rendezvous => Sync docs**

Do not begin execution until the user has reviewed and approved the plan when approval is requested.

## Study

Analyze the requested outcome and write a timestamped Markdown document in `doc/study/`. Discuss relevant tradeoffs, risks, external dependencies, and whether the feature should be implemented. Distinguish verified facts from assumptions and unresolved questions.

## Plan

After completing and reading the study, write a timestamped Markdown checklist in `doc/plan/`. The checklist is the basis for code writing. Keep the plan scoped to the approved outcome and make dependencies and verification steps explicit.

## Execute Plan

Follow the approved checklist. Scope each commit strictly to a conventional commit type and message (for example, `feat:`, `fix:`, or `chore:`). Do not combine unrelated changes.

## Rendezvous

Verify the implementation works and all unit tests pass. Merge the feature into the `main` branch only after verification succeeds. Report any test or integration blocker rather than claiming success.

## Sync Docs

Update the living documentation in `doc/wiki/` to reflect codebase changes and preserve the strategic and tactical decisions made.

## Exogenous Inputs

Pay particular attention to external artifacts, binary assets, and external API shapes. Capture real provider data streams as reference material before finalizing parsers or persistence formats. Record provenance and relevant request/response metadata, redact credentials and personal data, and clearly label missing or unverified inputs. Never present a synthetic example as a captured provider response.
