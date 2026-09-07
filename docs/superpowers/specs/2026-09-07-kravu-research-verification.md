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

## Recommended spec edits — APPLIED 2026-09-07 (commit follows)

All of the following were folded into `2026-09-04-kravu-design.md`:

1. **§7a ExploreJobs — robustness notes:** ATS endpoints named; wrong slug → HTTP 200
   empty (not 404); Lever `createdAt` epoch-ms vs ISO; LinkedIn easy-apply filter
   unreliable → `apply_type=easy-apply` is best-effort. ✅
2. **§7a ExpandJob — precision:** tier-1 JSON-LD is a direct
   `<script type="application/ld+json">` parse; `selectolax` for CSS; `trafilatura` for
   content cleanup; **LLM tier-3 receives flattened text, not raw HTML** (NEXT-EVAL). ✅
3. **§7a DraftCoverLetter:** `only_if_required` can under-trigger (~⅓ expect a letter even
   when unstated); `always` is the escape hatch. Draft-then-edit backed by arXiv 2509.25054. ✅
4. **§9 / LLM adapter:** `response_format` is provider-dependent → parse defensively,
   never assume JSON was honored. ✅
5. **Provenance:** cited Tam 2408.02442, ResumeFlow (SIGIR '24) 2402.06221, FaithJudge
   (EMNLP '25) 2505.04847, Qiu 2504.02870, NEXT-EVAL 2505.17125, the web-agent suite
   (WorkArena/BrowserArena/SafeArena/WAREX), the cover-letter DiD study, and SHRM
   "skillfishing" across §7a/§8/§9. ✅
6. **§8:** extended the UNVERIFIED flag from the model string to the Kiro/Cursor/Gemini
   CLI invocation flags (confirm each at build); `@playwright/mcp` tool layer confirmed. ✅

**Two additional evidence-based design changes adopted (new, from the deep-read):**

7. **Reasoning-first JSON key order** for all reasoning-bearing calls (ScoreJobFit,
   TailorResume, judge): schema lists reasoning/analysis fields **before** the
   score/verdict field. Basis: Tam et al. 2408.02442 (answer-before-reason collapses
   chain-of-thought). ScoreJobFit output reordered to
   `{reasoning, matched_keywords, missing_skills, score}`. ✅
8. **Instructed-JSON + defensive parsing** chosen over hard constrained-decoding as the
   binding JSON strategy for every LLM call (new §7a "JSON strategy" block). Basis:
   Tam 2408.02442 + provider-variance evidence (§9). ✅

**Bottom line:** the spec's decisions hold up against current research; the evidence
*strengthens* the safety-critical parts. The two design changes (#7, #8) and the input/
library precisions (#2) are the only substantive additions — all now in the spec and
ready for the implementation plan.


---

# Appendix A — Academic bibliography (deep-read), per step

This appendix records the **peer-reviewed / arXiv papers** read for each step, with the
precise finding and the concrete design consequence for kravu. Papers marked **[deep-read]**
were read in full; others were read at abstract/results level and are cited for support.
Engineering claims (JobSpy filters, ATS endpoints, CLI flags, LiteLLM behavior) are backed by
primary docs/READMEs in the main report above — those are correctly *not* academic-paper
claims.

## Step 1 — ExploreJobs (discovery, dedupe)

Mostly an engineering/ATS-docs domain (see main report §1). Academic backing is for the
**dedupe** decision specifically:

- **Fröbe et al., "The Impact of Main Content Extraction on Near-Duplicate Detection"** —
  arXiv 2111.10864. Finding: full-page content is *precision-oriented* for near-dup detection,
  main-content extraction is *recall-oriented*. Consequence: kravu's **normalized-URL primary
  key** is a cheap, high-precision exact-dedup first line; content-level near-dup (same job on
  two boards with different URLs) is a genuinely harder, separate problem — correctly out of
  v0.1 scope.
- **Silcock et al., "Noise-Robust De-Duplication at Scale"** — arXiv 2210.04261 (Harvard/
  Berkeley). Finding: near-dup detection over noisy text is non-trivial and benefits from
  learned methods. Consequence: confirms kravu should *not* attempt fuzzy cross-board content
  dedup in v0.1; URL normalization is the right scoped choice.

## Step 2 — ExpandJob (page → description extraction)

- **[deep-read] "NEXT-EVAL: Next Evaluation of Traditional and LLM Web Data Record
  Extraction"** — arXiv 2505.17125. Finding: **Flat JSON input** lets LLMs reach the best
  extraction accuracy (F1 = 0.9567) with **minimal hallucination**, beating Slimmed-HTML and
  Hierarchical-JSON inputs. Consequence: kravu's **LLM last-resort tier** should be fed
  *flattened / structured* text (e.g. cleaned text blocks or a flat field map), **not raw
  HTML** — a concrete refinement for `expand.py` / `playwright_page.py`.
- **"Extracting Structured Information From Complex Interactive Websites Using Executable LLM
  Agents"** — arXiv 2504.12682. Finding: even SOTA web agents get low recall (3–31%) on
  complex interactive sites. Consequence: strong support for kravu's **cascade ordering** —
  deterministic JSON-LD → CSS *first*, LLM only as a fallback, never an agent-driven crawl.
- **"ScrapeGraphAI-100k: A Large-Scale Dataset for LLM-Based Web Information Extraction"** —
  arXiv 2602.15189. Finding: LLM web extraction is now a mainstream, dataset-backed IR
  component. Consequence: validates having an LLM extraction tier at all.
- Tier-1 basis (non-paper): Google Search **JobPosting** structured-data docs (schema.org).

## Step 3 — ScoreJobFit (fit scoring)

- **[deep-read] Qiu et al., "AI Hiring with LLMs: A Context-Aware and Explainable Multi-Agent
  Framework for Resume Screening"** — arXiv 2504.02870 (CUHK / Imperial). Findings on 105
  HR-labeled resumes: best config correlates strongly with HR (Pearson PC10 = 0.84, Spearman
  SC10 = 0.74, MAE = 0.90; mean HR 7.68 vs LLM 7.76). **Ablation: structured extraction
  before evaluation measurably improves scoring.** Consequence: (a) LLM fit-scoring on a
  ~1–10 scale is validated; (b) kravu should feed **structured `ResumeFacts`** into
  ScoreJobFit (not raw text) — the ablation is direct evidence; (c) separating extraction /
  scoring / formatting improves explainability, matching kravu's matched/missing-keywords +
  reasoning output.
- **"Signal or Noise? Evaluating LLMs in Resume Screening…"** — arXiv 2507.08019. Finding:
  studies consistency (signal) vs random variation (noise) vs human experts. Consequence:
  supports **temperature 0 + score-once + retry** to suppress noise.
- **"Measuring Validity in LLM-based Resume Screening"** — arXiv 2602.18550. Finding: models
  don't reliably abstain between equally-qualified candidates and show demographic rate
  differences. Consequence: a **bias caveat** worth one line — kravu scores *for the user*
  (self-fit), not employer-side selection, so blast radius is lower, but the ranking is still
  LLM-derived and should be presented as advisory (which `status` + reasoning already do).
- **RubricRAG (arXiv 2603.20882)** and **"LLMs Designing and Applying Evaluation Rubrics"
  (arXiv 2602.08672)**. Findings: rubric-based evaluation is more interpretable; off-the-shelf
  LLM rubric *scoring reliability degrades in knowledge-intensive settings*, and closed models
  (GPT-4o) agree with humans more than open models. Consequence: kravu's explicit in-prompt
  **rubric** is supported; the temp-0 + clamp-to-1–10 + retry robustness is justified because
  open/local models (an explicit kravu option) are the less-reliable case.

## Step 4 — TailorResume (anti-fabrication, safety-critical)

- **[deep-read] Wu/Tam et al., "Let Me Speak Freely? A Study on the Impact of Format
  Restrictions on Performance of LLMs"** — arXiv 2408.02442 (Appier AI Research + NTU).
  Findings: **JSON-mode / constrained decoding significantly degrades reasoning tasks**;
  root cause observed was JSON-mode forcing the `answer` key *before* the `reason` key (100%
  of GPT-3.5-turbo responses), collapsing chain-of-thought; parsing errors were *not* the
  cause (near-zero parse failures, yet up to 38.15% accuracy gap); JSON-mode *helps*
  classification. Mitigations: looser format-restricting instructions, drop rigid schema,
  and **reason-first-then-answer key ordering**. Consequence (important, new): kravu's
  **score/tailor/judge prompts must place reasoning/analysis fields BEFORE the score/answer
  field**, and should prefer instructed-JSON over hard constrained-decoding for the
  reasoning-heavy calls. Reinforces the spec's existing "JSON is for parsing, not grounding"
  note with a concrete mechanism.
- **[deep-read] Zinjad, Bhattacharjee, Bhilegaonkar, Liu, "ResumeFlow: An LLM-facilitated
  Pipeline for Personalized Resume Generation and Refinement"** — **SIGIR '24** (arXiv
  2402.06221), DOI 10.1145/3626772.3657680. Findings independently arrived at three of
  kravu's core decisions: (a) the **personal-details section is passed through unchanged** —
  "we do not want the LLM to change any factual information … name, phone number, address"
  (= kravu's **code-injected header**); (b) **section-by-section** processing to avoid the
  *lost-in-the-middle* long-context failure (Liu et al. 2023); (c) explicit
  **content_preservation vs job_alignment** metrics, flagging *low preservation + high
  alignment* as "possibly hallucinated … unethical / dishonest." Consequence: strong,
  venue-published backing for kravu's fabrication guard and the `_REPORT.json` transparency
  artifact. Also references **AlignScore** (Zha et al. 2023) for factual consistency — a
  candidate technique for kravu's deterministic validator.
- **[deep-read] Tamber et al., "Benchmarking LLM Faithfulness in RAG with Evolving
  Leaderboards" (FaithJudge)** — arXiv 2505.04847, **EMNLP 2025 Industry Track** (Vectara).
  Finding: an **LLM-as-a-judge** framework using a pool of **human-annotated hallucination
  examples** substantially improves automated hallucination evaluation over prior methods
  (incl. Vectara's own HHEM model). Consequence: validates kravu's **always-on LLM judge**;
  and the judge prompt should include **exemplar fabrications** (few-shot) to sharpen it.
- **"Detecting Machine-Generated Career Trajectories via Multi-layer Heterogeneous Graphs"** —
  arXiv 2509.19677. Finding: LLMs generate convincing **fake résumé career trajectories**;
  detection methods are being built. Consequence: reinforces why kravu forbids inventing
  employers/roles/dates outright.

## Step 5 — DraftCoverLetter

- **[deep-read/abstract] "Evidence from Cover Letters" (AI writing tools and hiring)** —
  arXiv 2509.25054. Finding: a **difference-in-differences field study** shows access to an
  AI cover-letter tool **increased textual alignment** between letters and job posts and
  **raised callback rates**, and **time spent editing the AI draft is positively correlated
  with hiring success.** Consequence: the strongest single empirical backing for kravu's
  **draft-then-user-edits** model ("AI is the guide, you decide") and for the
  engineering-voice/JD-alignment mechanics — with the important nuance that *editing effort*
  matters, so kravu should present the draft as a starting point, not a finished artifact.
- **"A Practical Examination of AI-Generated Text Detectors"** (arXiv 2412.05139) and
  **"…Evidence from Explainable AI Beyond Benchmark Accuracy"** (arXiv 2603.23146). Finding:
  AI-text detectors are **unreliable in real-world settings**. Consequence: kravu's
  banned-words / anti-slop list is justified as a **writing-quality** measure (avoid generic
  AI phrasing recruiters skip), **not** as a claim to defeat detectors — the spec should not
  over-promise "undetectable."

## Step 6 — Apply Agent (use case 6)

- **[deep-read/abstract] "BrowserArena: Evaluating LLM Agents on Real-World Web Navigation
  Tasks"** — arXiv 2510.02418. Finding: on live open-web tasks, agents show **three
  consistent failure modes — CAPTCHA resolution, pop-up/banner removal, and direct URL
  navigation** — and behave inconsistently across models. Consequence: direct validation for
  kravu **parking CAPTCHA/login-wall jobs** and defaulting to a **human-approval gate**.
- **Drouin et al., "WorkArena: How Capable are Web Agents at Solving Common Knowledge Work
  Tasks?"** — arXiv 2403.07718. Finding: agents are promising but there is "a considerable
  gap towards full task automation," with open models lagging closed. Consequence: justifies
  **human-gate default** rather than autonomous submission, and the pluggable-driver design
  (closed-model drivers will perform better).
- **"SafeArena: Evaluating the Safety of Autonomous Web Agents"** — arXiv 2503.04957.
  Finding: dedicated safety benchmark (250 safe / 250 harmful tasks across five harm
  categories) for autonomous web agents. Consequence: supports kravu's safety framing — the
  agent must never fabricate answers or pursue harmful actions, and stays gated + capped.
- **"WAREX: Web Agent Reliability Evaluation on Existing Benchmarks"** — arXiv 2510.03285.
  Finding: real-world web is far less deterministic than sandboxed benchmarks. Consequence:
  justifies kravu's **per-job timeouts, retries, and attempt caps** in the runner.
- Tool layer (non-paper): Microsoft **@playwright/mcp** accessibility-snapshot server.

## Step 7 — Cross-cutting (structured output, judge, provider variance)

- **Tam et al. 2408.02442** (Step 4) — the core constrained-decoding-degrades-reasoning
  result; governs how *all* kravu JSON prompts are shaped.
- **NEXT-EVAL 2505.17125** (Step 2) — flat-input minimizes extraction hallucination;
  cross-cutting guidance for any LLM-parsing call.
- **FaithJudge 2505.04847** (Step 4) — cross-cutting basis for the judge pattern.
- Engineering (non-paper, see main report §7): LiteLLM `json_mode` docs + BerriAI issues
  #37720 / disc #11652 showing `response_format` is **silently dropped by some providers** —
  the empirical reason kravu must parse defensively regardless of the paper-level guidance.

## Honesty notes on this literature pass

- **Deep-read in full:** Tam 2408.02442, Qiu 2504.02870, ResumeFlow 2402.06221 (SIGIR '24).
  These carry the heaviest design weight (scoring + tailoring + JSON behavior).
- **Read at abstract/results level:** FaithJudge, NEXT-EVAL, BrowserArena, WorkArena,
  SafeArena, WAREX, the resume-screening validity/rubric papers, the cover-letter DiD study,
  and the dedup papers. Findings quoted are from abstracts/results sections; if you want any
  of these promoted to full deep-read before we cite them in the spec body, say which.
- **Venues:** ResumeFlow (SIGIR '24) and FaithJudge (EMNLP '25 Industry) are the clearest
  peer-reviewed venues; several others are arXiv preprints (2024–2026) — appropriate for a
  fast-moving area, but flagged as such rather than presented as archival publications.
- Steps 1 and 6's *mechanisms* (ATS endpoints, JobSpy filters, MCP, CLI flags) remain
  engineering facts verified against primary docs, not research claims — that separation is
  intentional.
