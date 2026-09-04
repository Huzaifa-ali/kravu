# kravu — Product & Ethics Principles

These are hard rules about what kravu does and does not do. They are
non-negotiable and protect users, the project's reputation, and its usefulness.

## kravu is a co-pilot, not a spam-bot

- The default behavior prepares materials and a ranked shortlist. It does NOT
  mass-submit applications.
- Autonomous form submission (stage 6) is an **opt-in, later-phase** module and,
  when built, defaults to a **human-approval gate** before anything is sent.
- Volume is not the goal. Fit and quality are. We never optimize for
  "applications sent" as a success metric.

## Never fabricate

- The tailoring stage may reorganize, re-emphasize, and select from the user's
  real resume facts. It must NEVER invent employers, titles, dates, degrees,
  metrics, or skills the user does not have.
- `Profile.resume_facts` is the ground truth. Tailoring is constrained to it.

## Respect platforms and privacy

- Discovery uses legitimate sources (public job-board data via JobSpy, or
  documented Apify actors). We do not build tooling whose purpose is to harvest
  private personal contact data at scale or to get users' accounts banned.
- No action that a reasonable maintainer would be embarrassed to defend publicly.

## Local-first and zero-friction

- kravu runs locally. Default storage is a single SQLite file — no server, no
  account, no cloud dependency required to get value.
- A new user must get value from just: a resume + a search + one (free-tier) LLM
  key. Everything else (Postgres, auto-apply, extra sources) is optional and
  layered on top. Setup friction kills adoption — guard against it.

## Provider-agnostic

- Any LLM provider works via LiteLLM. Gemini is the default only because it has a
  free tier. No stage may hardcode a specific provider or assume a specific model.

## Low slop

- YAGNI. Do not add abstractions, config knobs, or "flexibility" nobody asked for.
- Do not add pipeline stages to look sophisticated. Fold related work into
  existing stages. Fewer, well-separated stages = less drift surface.
- Prefer plain Python over frameworks where a framework adds indirection without
  earning it. We deliberately use NO agent framework for stages 1–5.
