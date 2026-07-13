# Codex Monitor Hardening Design

**Date:** 2026-07-13

**Status:** Approved for implementation

**Target:** Linux Mint Cinnamon 6.6+, Codex CLI 0.144.3 or compatible

## Purpose

Turn the existing Codex Monitor applet into a polished daily-use Cinnamon panel tool. The applet must show compact, centered quota meters in the panel, explain usage history in a useful dashboard, expose recent Codex sessions and safe terminal launch actions, manage the full currently available Remote Control lifecycle, and install and test cleanly without leaving duplicate applet entries.

The implementation remains one native Cinnamon applet with its bundled Python bridge. It does not add a continuously running service beyond the applet bridge or introduce a separate desklet.

## Panel Preview

### Base layout

The panel actor always displays two vertically centered rows:

```text
5h [usage bar]
 W [usage bar]
```

The label column has a fixed width and right-aligned text. Both bars begin at the same horizontal position and have the same dimensions. The two-row group is vertically centered within the available panel height instead of aligning to the top. Horizontal and vertical panels remain supported; horizontal layout is the primary optimized presentation.

### Dynamic state indicators

Small indicators appear to the right of the two-row meter only when they convey actionable state:

- A banked reset that is available but not near expiry shows `↻N`, where `N` is the available count.
- If any available reset expires within the configured warning window, the reset indicator becomes `⚠N` and receives warning styling. The tooltip names the nearest expiry and its countdown.
- Remote Control shows no panel indicator while disabled. When it is on, it shows a compact state indicator for connecting, connected, or errored. The tooltip always spells out the state; color is never the only signal.
- Stale data or a bridge error shows a compact warning indicator and stale styling without replacing the quota bars.

Indicators are composed dynamically so the base meter does not jump vertically. The applet accessible name and tooltip contain the same state in text. Quota thresholds still apply warning and critical styling to the meter.

## Dashboard Information Architecture

The popup remains a single scrollable dashboard organized in this order:

1. Header and live/stale state.
2. Five-hour and weekly quota cards.
3. Detailed usage graph.
4. Codex sessions and launch actions.
5. Banked resets.
6. Remote Control.
7. Last update, refresh, and settings actions.

The dashboard must fit a typical 1080p Cinnamon desktop without clipping. Long lists are bounded and use compact rows.

## Detailed Usage Graph

The graph supports Quota, Activity, and Both modes over 24 hours, 7 days, and 30 days.

### Required information

- A labeled Y axis. Quota uses a fixed 0–100% scale. Activity uses token counts in its legend and hover details while its plotted height is normalized to the visible peak.
- A labeled X axis with start, middle, and end local timestamps appropriate to the selected range.
- A legend identifying the five-hour, weekly, and activity series with their current, minimum, and maximum values.
- Reset markers at timestamps where a quota window reset changes, with a visible `R` marker and an explanatory legend entry.
- Pointer hover details for the nearest timestamp, including local time and every series value available at that point. Token values use compact formatting while retaining exact values in detail text.
- A clear empty state when no historical samples exist and an “insufficient history” state for a single sample.

Series processing and graph summaries live in pure JavaScript model functions so they can be tested outside Cinnamon. The drawing module handles coordinate transforms, painting, and pointer selection. Missing capabilities do not fabricate points.

## Codex Sessions And Launching

The bridge requests `thread/list`, sorted by most recently updated, and returns at most 12 normalized rows. Each row contains only:

- thread UUID;
- safe display title or short preview;
- working-directory display path;
- normalized source label;
- normalized status and attention flags;
- created and updated timestamps.

Session previews are never written to the quota-history file. The UI shows:

- **Active now** only for threads whose reported status is `active`, including approval or user-input attention states.
- **Recent / finished** for idle, not-loaded, and unavailable-to-the-monitor threads, ordered by last update.

A separate app-server process commonly reports sessions owned by VS Code or another Codex process as `notLoaded`. The applet labels these as “Ready to resume” and never claims they are currently active or definitively finished.

Clicking a session launches the Linux Mint default terminal through `x-terminal-emulator` with `codex resume <validated-thread-uuid>`. The row's existing working directory is used only if it is an absolute directory that currently exists. An **Open Codex** button launches `codex` in the default terminal. Commands use argument arrays with `shell=False`; neither session text nor a working-directory string is interpolated into a shell command.

Launch failures are returned as structured bridge errors and shown in the dashboard without crashing the applet.

## Remote Control

The dashboard calls the feature **Remote Control** without an “Experimental” badge or hidden experimental gate. Compatibility documentation may still note that the installed Codex CLI currently labels the underlying command experimental.

The Remote Control section is always present and supports:

- read connection status (`disabled`, `connecting`, `connected`, `errored`);
- start after explicit confirmation;
- stop;
- begin pairing and show the manual and automatic pairing code, environment, and expiry countdown;
- poll pairing claim status until claimed or expired;
- list paired clients for the active environment with device name/type, platform, app version, and last-seen time when supplied;
- revoke a selected client after explicit confirmation;
- refresh status and clients after every state-changing action.

Pairing codes remain memory-only and are never logged, persisted in history, placed in test snapshots, or included in final smoke-test output. External Remote Control responses are shape-validated and unknown fields are discarded. If the installed CLI lacks a method, the UI reports the capability as unavailable while keeping quota monitoring functional.

The applet polls Remote Control status only while the feature is connecting/connected or pairing is active. Disabled state does not create unnecessary high-frequency requests.

## Bridge Interface

The newline-delimited JSON bridge adds these validated actions while preserving existing actions:

| Action | Input | Output |
| --- | --- | --- |
| `sessions` | `{ limit?: 1..50 }` | `{ active: Session[], recent: Session[] }` |
| `open_codex` | `{}` | `{ launched: true }` |
| `open_session` | `{ threadId: UUID, cwd?: string }` | `{ launched: true }` |
| `remote_pair_start` | `{}` | normalized pairing record |
| `remote_pair_status` | `{ pairingCode?: string, manualPairingCode?: string }` | `{ claimed: boolean }` |
| `remote_clients` | `{ environmentId: string }` | `{ clients: RemoteClient[] }` |
| `remote_revoke` | `{ environmentId: string, clientId: string, confirmed: true }` | normalized result |

Identifiers and bounds are validated at the protocol boundary. Runtime and Codex failures return existing structured, non-sensitive error responses. The older `remote_pair` action may remain as a compatibility alias for one release but the applet uses `remote_pair_start`.

## Installation And Cleanup

`scripts/install.sh` stages the applet atomically as today, but stores the previous installation under:

```text
${XDG_DATA_HOME:-$HOME/.local/share}/codex-monitor@breixopd/install-backups/
```

Backups must never live in `cinnamon/applets`, because Cinnamon treats every directory there as an applet candidate. During installation, stale directories matching `codex-monitor@breixopd.backup-*` are removed from the Cinnamon applets directory after their exact UUID/prefix is checked. The installer leaves one discoverable applet directory.

## Testing And Live Verification

### Automated tests

Python tests cover thread normalization and classification, terminal command construction, UUID/path validation, launch failures, all Remote Control methods, response validation, pairing claim state, client normalization, revoke confirmation, and protocol compatibility.

JavaScript tests cover panel badge priority/composition, reset-expiry warnings, Remote state visibility, graph axes and summaries, range filtering, nearest-point hover selection, token formatting, and empty/single-sample states.

The existing validation, packaging, and syntax checks remain green.

### Live Cinnamon smoke test

A repeatable smoke script installs the current source, reloads the applet, and verifies through Cinnamon's D-Bus evaluation surface that:

- exactly one Codex Monitor applet directory is discoverable;
- the extension is loaded with no recorded Cinnamon error;
- the bridge returns a quota snapshot and sessions;
- the panel actor is vertically centered and both bar rows share the same geometry;
- every graph mode and range renders without an exception and exposes non-empty labels when data exists;
- the dashboard opens and session/Remote Control sections exist;
- default-terminal launch argument generation is valid without leaving a Codex TUI running;
- Remote Control can complete start, status, pairing-start, pairing-status, and client-list checks while leaving the live daemon running; stop behavior is verified only in isolated tests because stopping the daemon can terminate the active Codex session;
- pairing codes and account identity are absent from captured logs and fixtures.

Panel and dashboard screenshots are inspected at the final installed version. Live smoke failures block the merge.

## Error Handling And Compatibility

Quota monitoring is the primary capability. Sessions, token activity, reset credits, and Remote Control degrade independently when unsupported. The dashboard names the unavailable capability and continues showing valid data from other sections.

The bridge retains bounded timeouts and restart backoff. UI lists cap their row counts, labels truncate safely, and graph work is bounded by retained history. All newly rendered external strings are treated as plain label text.

## Completion Criteria

The work is complete only when automated tests, package validation, security/code review, and the installed Cinnamon smoke test pass; screenshots confirm centered panel geometry and useful graph labeling; stale installed copies are gone; the working tree is clean; and the feature branch is merged locally into `main`. No pull request, push, tag, or public release is part of this change.
