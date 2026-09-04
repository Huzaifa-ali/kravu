# kravu

**A local-first, open-source job-hunting pipeline.** Point it at your resume and a
search, and it discovers matching roles, scores each one against your CV, and
hands you a tailored resume plus a ranked shortlist of the jobs actually worth
your time — so you spend your effort applying, not searching.

> kravu is a **co-pilot, not a spam-bot.** v0.1 prepares materials and a shortlist;
> it does not blast applications. Autonomous form submission is a later, opt-in module.

---

## Why

Job hunting for engineers is mostly mechanical: find roles, read each JD, judge
fit, re-tailor the resume, repeat. kravu automates the mechanical 80% and leaves
the decision (and the actual "apply") to you.

## What it does (v0.1)

A deterministic pipeline of independent stages, coordinated through a local
SQLite database. Each stage does one thing and writes its result back:

| Stage | What happens |
|-------|--------------|
| 1. **discover** | Find job postings across boards (via JobSpy), dedupe by URL |
| 2. **enrich**   | Fetch each job's full description |
| 3. **score**    | LLM rates fit 1–10 against your profile; only high-fit jobs proceed |
| 4. **tailor**   | LLM rewrites your resume per job — reorganizes and emphasizes, never fabricates |
| 5. **cover**    | LLM writes a targeted cover letter (only when the role needs one) |

Output: a ranked shortlist + tailored materials you review and send yourself.

## Design principles

- **Deterministic where possible.** Stages 1–5 are plain Python. The LLM is used
  only as a focused text function (score this / rewrite that), one job at a time —
  never a giant prompt, so no context drift.
- **Provider-agnostic.** Any LLM via [LiteLLM](https://github.com/BerriAI/litellm):
  Gemini (default, free tier), OpenAI, Anthropic, Ollama, Cohere, and more.
- **Local-first.** SQLite, one file, zero setup. No server, no account.
- **Honest.** Never fabricates resume facts. Never mass-submits. Never harvests
  private contact data.

## Status

🚧 Early development. v0.1 (discover → tailor → shortlist) in progress.

## License

See [LICENSE](LICENSE).
