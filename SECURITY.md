# Security Policy

## Supported versions

kravu is in early development (v0.1). Security fixes are applied to the latest
`main`. There are no long-term support branches yet.

| Version | Supported |
|---------|-----------|
| `main` (v0.1.x) | ✅ |
| older            | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately using one of:

- GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  (the **Security** tab → *Report a vulnerability*), or
- Email the maintainer at **huzaifaali4013399@gmail.com** with the subject
  `kravu security`.

Please include: a description of the issue, steps to reproduce, the affected
version/commit, and the potential impact. You can expect an acknowledgement
within a few days. Once a fix is available, we will credit reporters who wish to
be named.

## Scope and things to keep in mind

kravu is **local-first** and runs on the user's own machine:

- **API keys are never stored by kravu.** They are read from the user's
  environment or `~/.kravu/.env`. Keys, resume data, and generated materials stay
  local. Reports about kravu writing, logging, or transmitting keys are in scope
  and high priority.
- **The Apply Agent drives a real browser.** It is opt-in and human-gated by
  default. Issues that could cause it to submit without approval, bypass the daily
  cap, or fabricate answers to application questions are in scope.
- **kravu executes external coding-agent CLIs and an MCP server.** Reports of
  command injection, unsafe argument handling, or SSRF-style fetches are in scope.
- **Untrusted input** (job pages, LLM output, ATS API responses) is treated as
  data. Reports where such content can trigger code execution, path traversal, or
  SQL injection are in scope.

Out of scope: vulnerabilities in third-party dependencies (report those upstream),
and misconfiguration of a user's own environment or provider keys.
