# ADR-001: Use the Codex app-server as the usage boundary

## Status

Accepted

## Date

2026-07-13

## Context

The applet needs current quotas, reset credits, activity, and Remote Control state. Reading authentication files, scraping terminal output, or reimplementing Codex authentication would be brittle and would expose more private data than the UI needs.

## Decision

Run a local, long-lived Python helper that starts `codex app-server` and talks to its JSON-RPC API over standard input/output. The helper normalizes responses into a small JSONL protocol for the Cinnamon process. It never reads Codex credentials and never starts a network listener.

The baseline is Codex CLI 0.144.3. Optional methods degrade gracefully when older versions return method-not-found.

## Alternatives considered

- Parse Codex CLI text output: rejected because formatting is not a stable interface.
- Read files under `CODEX_HOME`: rejected because credential and state formats are private implementation details.
- Call an OpenAI web endpoint directly: rejected because it would duplicate authentication and require secret handling in the applet.

## Consequences

- Codex remains the authority for authentication and quota semantics.
- Compatibility depends on app-server method stability, so the bridge validates response shapes and reports a stale state on errors.
- The Cinnamon UI stays responsive because RPC runs in a helper process.
