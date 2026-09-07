# kravu — Spec Research Verification

**Date:** 2026-09-07
**Purpose:** Verify each spec decision (use cases 1–6 + cross-cutting stack) against
current (2025–2026) AI/hiring research and primary technical sources, before writing
the implementation plan.
**Scope:** `docs/superpowers/specs/2026-09-04-kravu-design.md`.
**Verdict:** Every material design decision is **confirmed** or **strongly supported**
by external evidence. No decision was contradicted. A handful of implementation-precision
notes and two "confirm-at-build" items (default model string, Kiro/Cursor/Gemini CLI
flags) are flagged. None block planning.

Legend: ✅ Confirmed · 🟢 Strongly supported · ⚠️ Confirm at implementation · 📝 Precision note

---

## 1. ExploreJobs (spec §7a, §13a) — ✅ Confirmed

**ATS public JSON endpoints** — confirmed live (Aug 2026), no key/proxy/anti-bot:
- Greenhouse: `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs`
- Lever: `GET https://api.lever.co/v0/postings/{token}?mode=json`
- Ashby: `GET https://api.ashbyhq.com/posting-api/job-board/{token}`
- Source: [Six ATS platforms publish their job boards as open JSON](https://dev.to/udaninn/six-ats-platforms-publish-their-job-boards-as-open-json-here-are-the-endpoints-2d3k) (dev.to, Aug 2026).

Confirms spec claims: slug validation + drop-if-invalid, keywords-primary/ATS-optional,
per-record isolation.

**JobSpy validation rules** — confirmed **exactly** against the
[JobSpy README](https://github.com/speedyapply/JobSpy):
- Indeed: only one of `hours_old` | (`job_type` + `is_remote`) | `easy_apply`.
- LinkedIn: only one of `hours_old` | `easy_apply`.
- `country_indeed` required for Indeed/Glassdoor; Google needs a specific `google_search_term`;
  429 blocking → proxies; ~1000-job cap per search; structured `location{country,city,state}` + `is_remote`;
  `description_format` markdown default.

**📝 Notes for the plan (robustness, not spec errors):**
- Wrong ATS slug returns **HTTP 200 with an empty list**, not 404 — "not on this ATS"
  and "typo" are indistinguishable from the response. Validate by trying the platform
  and treating empty as a real (reportable) outcome.
- Lever `createdAt` is **epoch-ms**, while Greenhouse/Ashby use ISO-8601 — normalize or
  an `hours_old`-style filter silently returns nothing for Lever.
- Greenhouse `/jobs` omits department; needs a second `/departments` call to join.
- ⚠️ JobSpy README notes the **LinkedIn easy-apply filter "no longer works"** → treat
  `apply_type = easy-apply` derived from LinkedIn as best-effort, not authoritative.

---

## 2. ExpandJob (spec §7a) — ✅ Confirmed

**JSON-LD → CSS → LLM cascade ordering** matches current best practice:
- `schema.org/JobPosting` JSON-LD is the standardized, durable path — required by
  [Google's Job Posting structured-data docs](https://developers.google.com/search/docs/appearance/structured-data/job-posting);
  2026 scraping guidance explicitly says "parse JSON-LD, not CSS selectors" because
  script-embedded data outlives front-end markup ([scrapfly](https://scrapfly.io/blog/posts/how-to-scrape-ticketmaster), [instantproxies](https://instantproxies.com/blog/extract-json-ld-and-script-embedded-data/)).
- `selectolax` = fast Lexbor/CSS-selector parser (tier-2 CSS); `trafilatura` = main-content
  extractor ([decodo 2026](https://decodo.com/blog/python-extract-text-from-html): "selectolax for large-scale extraction … Trafilatura when you only want the article body").
- LLM last-resort tier for unknown layouts fits the scraper-plus-model pattern.

**📝 Precision note for the plan:** `trafilatura` is a boilerplate-removal/main-content
extractor, **not** a JSON-LD parser. Implement tier-1 JSON-LD as a stdlib `json.loads`
over `<script type="application/ld+json">` blocks; use `trafilatura` for content cleanup,
`selectolax` for CSS. The spec's grouping is fine; the plan should assign libraries precisely.

Playwright render-first (no httpx fallback) is sound for JS-heavy/blocked job pages.

---

## 3. ScoreJobFit (spec §7a) — 🟢 Strongly supported

**"Aggressive keyword hard-filters wrongly reject good fits"** is well-evidenced:
- Harvard-cited "~88% of employers' systems reject qualified talent due to keyword
  mismatch" ([pin.com](https://www.pin.com/blog/semantic-search-recruitment/)).
- A 2025 peer-reviewed *Information Sciences* study: semantic matching beat keyword
  methods ~2:1 across SWE/data-science/Hadoop roles (same source).
- Multiple 2026 sources describe "ATS 2.0" moving from binary keyword logic to semantic
  matching ([theinterviewguys](https://blog.theinterviewguys.com/what-semantic-matching-means/), [mycvcreator](https://www.mycvcreator.com/blog/ats-2-0-semantic-matching-how-ai-reads-resumes), [hireflow](https://hireflow.net/blog/why-ats-rejects-qualified-candidates)).

**Rubric-driven LLM evaluation + strict JSON + temp-0** is the current research direction:
- [ACL/EACL 2026 demo](http://acl.ldc.upenn.edu/2026.eacl-demo.24/): "role-specific,
  LLM-generated rubrics … unlike traditional ATS keyword matching."
- ResumeAdapter methodology (2026): "treat a resume as text and you're at the mercy of
  temperature; treat it as a typed object with validated schemas and deterministic
  comparison and … invented job titles, dropped certifications, fabricated metrics
  disappear" — supports temp-0 + strict JSON here **and** the TailorResume guard.

**📝 Nuance:** real 2026 ATS run **hybrid** pipelines (semantic for responsibilities +
hard filters for credentials/eligibility/work-auth) ([hireflow, semantic-matching 2026](https://hireflow.net/blog/semantic-matching-ats-2026)). kravu keeping categorical
location/remote in ExploreJobs and holistic fit in ScoreJobFit matches this. Aligned.

---

## 4. TailorResume — anti-fabrication (spec §7a, principles.md) — ✅ Confirmed (safety-critical)

All three load-bearing claims are backed by peer-reviewed / documented sources:

1. **"Strict JSON is for parsing, not grounding; JSON-alone can worsen hallucination."**
   - Tam et al. 2024, ["Let Me Speak Freely?"](https://arxiv.org/html/2408.02442v2):
     stricter format constraints degrade reasoning (~10–15% on reasoning tasks per
     [summary](https://medium.com/@michael.hannecke/beyond-json-picking-the-right-format-for-llm-pipelines-b65f15f77f7d)).
   - [ICML 2026 "Structured Hallucination in Tool-Using Agents"](https://openreview.net/forum?id=CaJudGHxoR)
     and [TDS 2026 "Your JSON Is Valid but Your Data Is Wrong"](https://towardsdatascience.com/your-json-is-valid-but-your-data-is-wrong-five-failure-modes-llm-structured-outputs-wont-catch/):
     valid JSON can carry silently-corrupted field values with no error signal.
   - → Validates the spec's explicit note that grounding comes from the two checks, not JSON.

2. **Two-layer guard (deterministic validator + always-on LLM judge).**
   - Reference-free LLM-as-judge for faithfulness is established: [FaithJudge (arxiv 2505.04847)](https://arxiv.org/abs/2505.04847),
     [Real-Time RAG eval models (arxiv 2503.21157)](https://arxiv.org/abs/2503.21157).
   - Crucially, [arxiv 2508.08285](https://arxiv.org/html/2508.08285v2): lexical metrics
     (e.g. ROUGE) have high recall but very low precision; detection methods drop up to
     45.9% under human-aligned (LLM-judge) evaluation → "lexical checks miss fluent lies"
     → validates pairing a cheap deterministic pass with an always-on semantic judge.

3. **"Skillfishing" — zero-fabrication, no adjacent/learnable-skill tolerance.**
   - Confirmed real, widely-documented 2026 hiring phenomenon: [SHRM](https://www.shrm.org/executive-network/insights/rise-of-skillfishing-what-hr-leaders-need-to-know-now),
     [BuiltIn](https://builtin.com/articles/what-is-skillfishing), [Glider.ai](https://glider.ai/skillfishing-the-new-recruiting-trend/),
     HR Dive (May-2026 feature), [Boston.com](https://www.boston.com/news/job-doc/2026/04/23/what-is-skillfishing/).
     Candidates overstating skills (esp. AI fluency) "fall apart on day one," and sources
     explicitly name AI-generated tailored resumes/cover letters as a driver.
   - → Directly validates code-injected header + validator + judge + no-stretch honesty line.

---

## 5. DraftCoverLetter (spec §7a) — 🟢 Strongly supported

- **Policy-based (`only_if_required` default) over blanket-writing:** only ~10–20% of
  postings require a cover letter (as little as ~2% of ads even mention one) — "no longer
  a default must-attach" ([crownstaffing](https://www.crownstaffing.com/cover-letters-in-the-ai-era/),
  [staffingbystarboard](https://staffingbystarboard.com/blog/cover-letters-in-2026-still-worth-writing/), [hireflow](https://hireflow.net/blog/do-cover-letters-matter-2026)).
  Validates rejecting ApplyPilot's write-for-every-job.
- **Generic AI letters get skipped; specific ones help:** [Forbes, 6 recruiters, June 2026](https://www.forbes.com/sites/carolinecenizalevine/2026/06/14/do-cover-letters-still-matter-6-recruiters-weigh-in/)
  ("generic, AI-generated letters get skipped; a short, specific note … shows judgment").
  Validates engineering-voice mechanics + banned-words / zero-fabrication.
- **When required, they matter:** early-2026 survey of 650 hiring pros — 68% consider them
  important in some capacity, 75% want them customized, 33% expect one even when "optional"
  ([interninsider](https://staging.interninsider.me/blog/cover-letters-for-internships)).

**📝 Note:** the "33% expect one even when optional" figure means pure JD-text "required"
detection can under-trigger; the spec's user-selectable `always` policy covers this. Worth
one sentence in §7a documenting the limitation of `only_if_required`.

---

## 6. Apply Agent — use case 6 (spec §8) — ✅ Confirmed (2 items ⚠️ confirm-at-build)

- **`@playwright/mcp` is real:** official [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)
  / [playwright.dev/mcp](https://playwright.dev/mcp/introduction) — browser automation via
  structured accessibility snapshots (no vision model), npx-runnable. Matches §8 exactly.
- **Per-agent config formats:** Codex is **TOML, not JSON** — confirmed
  ([designrevision 2026](https://designrevision.com/blog/add-mcp-server-to-codex): "Codex's
  config is TOML, not JSON — the format Claude Code and Cursor use won't work here";
  [mejba.me](https://www.mejba.me/blog/configure-mcp-server-permissions-codex-cli-laravel):
  "Codex CLI does not read an mcp.json file"). Validates "Codex=TOML, others=JSON,
  encapsulated per driver."
- **Claude Code headless flags:** confirmed from [official docs](https://docs.claude.com/en/docs/claude-code/sdk/sdk-headless):
  `claude -p`, `--output-format text|json|stream-json`, `--mcp-config`, `--allowedTools`.
- **Pluggable driver Strategy is a recognized pattern:** headless-cli, ai-cli-mcp,
  cursor-headless all normalize per-agent flags/output-formats/config shapes.

**⚠️ Confirm at implementation (same class as the model-string flag):**
- **Kiro driver** invocation (`kiro --no-interactive`) — first-party/internal; not
  publicly documented in search. Verify against the installed Kiro CLI at build.
- **Cursor** (`cursor-agent -p --output-format stream-json --approve-mcps`) and **Gemini**
  (`gemini -p --output-format json`) flags appear in community tooling and match the general
  pattern, but pin each to its official CLI docs when writing that driver.

Human-gate default + daily cap + CAPTCHA/login/custom-question parking (never fabricated)
is consistent with principles.md and the skillfishing findings.

---

## 7. Cross-cutting: LLM stack & providers (spec §9, §10) — ✅ Confirmed (1 caveat)

- **LiteLLM structured JSON:** confirmed — [json_mode docs](https://docs.litellm.ai/docs/completion/json_mode)
  support `response_format={"type":"json_object"}` and json_schema; `gemini` is a listed
  provider; unified OpenAI-format interface to 100+ LLMs.
- **⚠️ Provider-dependent caveat (reinforces the design):** structured output is **not**
  uniformly honored — some providers silently drop `response_format` and return prose while
  reporting success ([litellm #37720](https://github.com/BerriAI/litellm/issues/37797/linked_closing_reference),
  [disc #11652](https://github.com/BerriAI/litellm/discussions/11652)). The plan must parse/validate
  defensively and treat unparseable output as a failure path — which ScoreJobFit
  (retry+clamp) and TailorResume (validator+judge) already do. No spec change needed;
  reinforce in the LLM adapter.
- **Default model string:** Gemma 4 **exists** (Google/DeepMind/Google Cloud, Apache-2.0),
  but the confirmed size is **Gemma 4 12B**; I did **not** find a "Gemma 4 31B" size or the
  exact LiteLLM string `gemini/gemma-4-31b`. This corroborates the spec's existing UNVERIFIED
  flag. Provider-prefix convention (`gemini/…`, `ollama/…`) is correct.
- **Ollama Qwen tags** (`qwen3.5:4b`, `qwen3.8:27b`) are plausible but unverified version
  strings — same "model strings move / overridable via `KRAVU_MODEL`" caveat. Fine.
- **Pinned package versions** (litellm 1.99, python-jobspy 1.1.82, playwright 1.62, …) are
  forward-plausible for the 2026-09-04 snapshot and use compatible-release ranges; `uv.lock`
  will capture exact resolved versions. Low risk.

---

## Recommended spec edits (small, optional — for your approval)

1. **§7a ExploreJobs — add robustness notes:** wrong ATS slug → HTTP 200 empty (not 404);
   Lever `createdAt` epoch-ms vs ISO; Greenhouse department join; LinkedIn easy-apply filter
   unreliable → `apply_type=easy-apply` from LinkedIn is best-effort.
2. **§7a ExpandJob — precision:** state that tier-1 JSON-LD is a direct
   `<script type="application/ld+json">` parse; `trafilatura` is for content cleanup,
   `selectolax` for CSS.
3. **§7a DraftCoverLetter — one sentence:** note that `only_if_required` can under-trigger
   (some employers expect a letter even when "optional"); `always` is the escape hatch.
4. **§9 / LLM adapter — one sentence:** `response_format` support is provider-dependent; the
   adapter parses/validates defensively and never assumes JSON was honored.
5. **Provenance (optional):** cite Tam et al. 2024, FaithJudge, and SHRM "skillfishing" in
   §7a/principles.md so the anti-fabrication design's research basis is documented.
6. **§8 — extend the UNVERIFIED flag** already applied to the model string to also cover the
   Kiro/Cursor/Gemini CLI invocation flags (confirm against each CLI at build).

**Bottom line:** the spec's decisions hold up against current research. The evidence
*strengthens* the safety-critical parts (anti-fabrication two-layer guard, holistic scoring,
policy-based cover letters, human-gated apply). Nothing here requires a redesign; the notes
above are refinements to fold into the implementation plan.
