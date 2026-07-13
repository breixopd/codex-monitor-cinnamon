# ADR-002: Keep sensitive state ephemeral and confirm mutating actions

## Status

Accepted

## Date

2026-07-13

## Context

The usage graph needs samples across sessions. Applying reset credits, enabling Remote Control, revoking a client, and installing a Codex update can change account or machine state. Pairing payloads and updater diagnostics must not become durable monitor data.

## Decision

Store only quota percentages, reset timestamps, and capture timestamps in a mode-`0600` JSONL file under the user's XDG data directory. Store the last successful release version and check time separately in a mode-`0600` JSON file. Do not persist account identity, token activity, pairing codes, client details, installer content, or command output.

Reset-credit consumption, Remote Control start/revocation, and update installation require a visible Cinnamon confirmation. Each reset request receives a fresh idempotency UUID. Commands use fixed argument arrays with `shell=False`; the updater never constructs a shell pipeline and suppresses process output. Errors shown to the UI are sanitized.

Read-only update discovery runs after the first quota snapshot and every 12 hours. It uses Codex's fresh local version cache or the bounded official GitHub latest-release response. Installation prefers `codex update`; older standalone releases fall back to a privately downloaded official installer file executed with `/bin/sh` and `CODEX_NON_INTERACTIVE=true`. Updates never restart Remote Control, Cinnamon, the bridge, or existing sessions.

Pairing codes and generated SVG stay in memory. The bridge is the sole QR generator, and the dashboard clears the SVG and manual code when pairing completes or expires.

## Alternatives considered

- Store complete snapshots: rejected because it retains unnecessary account and activity data.
- Put history in dconf: rejected because append/prune workloads and migration are simpler in a private JSONL file.
- Enable Remote Control automatically: rejected because it expands the control surface of the machine.
- Install updates automatically: rejected because replacing a developer tool must remain an explicit user decision.
- Pipe the installer from `curl` into a shell: rejected because a private bounded file gives clear validation, permissions, cleanup, and argument boundaries.

## Consequences

- Removing `$XDG_DATA_HOME/codex-monitor@breixopd/history.jsonl` resets the graph without affecting Codex.
- History is device-local and is not synchronized.
- Removing `update-state.json` forgets the last monitor-owned release result without changing Codex.
- Update checks can fail offline without affecting quota, sessions, or Remote Control.
- Live verification must never stop Remote Control because doing so can terminate the Codex session running the verification.
