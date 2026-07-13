# ADR-002: Keep history local and gate mutating actions

## Status

Accepted

## Date

2026-07-13

## Context

The usage graph needs samples across sessions, while applying reset credits and enabling Remote Control can change account or machine state.

## Decision

Store only quota percentages, reset timestamps, and capture timestamps in a mode-0600 JSONL file under the user's XDG data directory. Do not persist account identity, token activity, pairing codes, or command output.

Reset-credit consumption and Remote Control start require a visible Cinnamon confirmation. Each reset request receives a fresh idempotency UUID. Commands use fixed argument arrays with `shell=False`; errors shown to the UI are sanitized. Remote Control is disabled in settings by default, and pairing codes remain in memory.

## Alternatives considered

- Store complete snapshots: rejected because it retains unnecessary account and activity data.
- Put history in dconf: rejected because append/prune workloads and migration are simpler in a private JSONL file.
- Enable Remote Control automatically: rejected because it expands the control surface of the machine.

## Consequences

- Removing `$XDG_DATA_HOME/codex-monitor@breixopd/history.jsonl` resets the graph without affecting Codex.
- History is device-local and is not synchronized.
- The remote feature remains explicitly experimental and opt-in.
