"""Adapters layer: concrete infrastructure implementing domain ports.

Everything that talks to the outside world lives here — the SQLite store, the
LiteLLM client, HTTP fetchers, and the JobSpy discovery source. Services depend
on the domain ports these adapters implement, never on the adapters directly.
"""
