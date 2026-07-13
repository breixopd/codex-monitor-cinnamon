# Codex Monitor Clarity, Graph, QR, and Updates Design

**Date:** 2026-07-13

**Status:** Approved

## Goal

Make every dynamic panel state understandable at a glance, replace misleading graph interpolation with truthful visual encodings, consolidate QR generation into one implementation, and add safe automatic Codex update discovery with a user-triggered background update.

## Product Principles

- The compact panel remains two centered quota rows and gains symbols only for actionable states.
- Color never carries meaning alone. Every symbol has explicit dashboard and tooltip text.
- Graph geometry represents the underlying data semantics instead of merely connecting samples.
- Update checks are automatic and read-only. Installing an update always requires a user click and confirmation.
- Pairing codes and QR content stay in memory and never enter logs, screenshots, history, or update state.
- Live verification never stops Codex Remote Control or restarts its daemon.

## Panel Indicators

The existing quota thresholds remain user-configurable. The applet calculates a normalized indicator list and uses it for panel badges, accessible text, dashboard explanations, and the applet tooltip.

| Condition | Panel symbol | Severity | Explanation |
| --- | --- | --- | --- |
| Quota at warning threshold | `!` | warning/amber | `Weekly quota warning: 74% used` |
| Quota at critical threshold | `!` | critical/red | `Weekly quota critical: 94% used` |
| Banked reset available | `↻N` | informational | `2 banked resets available` |
| Banked reset nearing configured expiry threshold | `⚠N` | warning/amber | `Banked reset expires in 2d 3h` |
| Banked reset expires within six hours | `⚠N` | critical/red | `Banked reset expires in 4h` |
| Remote connecting | `◐` | warning/amber | `Remote Control connecting` |
| Remote connected | `●` | success/green | `Remote Control connected` |
| Remote errored | `!` | critical/red | `Remote Control error` |
| Snapshot stale | `!` | critical/red | `Usage data stale` |

Separate style classes are applied to each badge actor. A quota warning no longer relies only on tinting the complete panel container. Vertical panels continue to hide text badges and show the compact bar fallback.

The dashboard header receives a compact `Current indicators` row. It renders only active, meaningful states as plain-language chips. When no action is needed it shows `Usage data current`. The same explanations are included in the applet tooltip and accessible name.

## Graph Semantics

### Quota

- Quota history renders as a stepped line: horizontal until the next reading, then vertical at that reading.
- A reset-time transition creates an `R` marker and a deliberate vertical change.
- A gap larger than the range-specific continuity threshold starts a new segment:
  - 24 hours: two hours.
  - 7 days: twelve hours.
  - 30 days: thirty-six hours.
- No diagonal line connects samples across a gap or reset.

### Activity

- Daily token activity renders as bars rather than a line.
- Activity-only mode uses a token-count Y axis based on the visible maximum.
- Combined mode uses quota percentages on the left axis and token counts on the right axis.
- The legend and hover details always show exact token values. Relative height is never labeled as a percentage of quota.

### Downsampling and Interaction

- Graph work remains bounded to 1,200 quota points per series.
- Downsampling preserves first and last samples, reset transitions, and each time bucket's minimum and maximum.
- Hover uses the cursor timestamp and rejects distant samples.
- The cursor guide remains visible while hovering.
- Empty, single-sample, and gap-heavy ranges have explicit states instead of misleading lines.

## QR Consolidation

The Python bridge becomes the sole QR generator. It creates a high-contrast SVG with a standards-compliant four-module quiet zone using the optional system `python3-qrcode` package.

The bridge returns a bounded `qrSvg` string. The Cinnamon UI displays it with native in-memory image/icon support. The custom matrix JSON and custom Cairo QR renderer are removed, including `qr.js`, `qrMatrix`, and their tests.

If SVG generation or native rendering is unavailable, the manual pairing code remains visible with `QR unavailable; use the manual code`. Pairing completion and expiry clear both the SVG and manual code from UI memory.

## Automatic Update Discovery

The updater exposes three separate operations:

1. `update_status` returns installed version, latest known version, check freshness, availability, and any active update result.
2. `update_check` performs a read-only refresh when needed.
3. `update_start` requires explicit confirmation and starts the background update.

### Check Source and Cadence

- Check once during applet startup and then every twelve hours.
- Read `$CODEX_HOME/version.json` first when its `last_checked_at` value is no older than twelve hours.
- Otherwise request `https://api.github.com/repos/openai/codex/releases/latest`, the same primary release endpoint used by the official standalone installer.
- Send a fixed user agent, enforce a ten-second timeout and a one-megabyte response limit, and accept only a bounded `rust-vX.Y.Z` tag.
- Compare parsed numeric semantic-version components. Pre-release versions never replace a newer stable version accidentally.
- Keep network failure non-fatal and retain a last-known successful result in an applet-owned `update-state.json` file with mode `0600`.
- Never write to Codex's own `version.json`.

No update badge appears in the panel. When current, the dashboard shows only the installed version. When newer, it shows `Codex X → Y` and an `Update Codex…` button.

## Background Update

Clicking `Update Codex…` opens a confirmation dialog naming the installed and target versions. After confirmation:

- Prefer the installed binary's stable `codex update` command.
- If self-update is unavailable on an older standalone release, download the official `https://chatgpt.com/codex/install.sh` script to a private temporary file and execute it with `/bin/sh` and `CODEX_NON_INTERACTIVE=true`.
- Never construct a shell pipeline and never interpolate version or path data into a shell command.
- Run the updater asynchronously so quota, session, and Remote polling remain responsive.
- Bound stdout/stderr, sanitize all UI errors, and never display raw updater diagnostics.
- Prevent concurrent checks or updates.
- On success, re-read `codex --version`, refresh update state, and show `Updated to Codex X. New Codex launches use this version.`
- Do not stop or restart Remote Control, Cinnamon, the main bridge, or existing Codex sessions.

Update discovery is automatic; installation is never automatic.

## UI Placement

The version/update row lives in the dashboard footer above the existing refresh status. Its states are:

- `Codex 0.144.3` when current.
- `Codex 0.144.3 → 0.145.0` plus `Update Codex…` when available.
- `Updating Codex…` with the action disabled while running.
- `Updated to Codex 0.145.0` after success.
- `Update failed; Codex 0.144.3 is still installed` plus `Retry` after a sanitized failure.

The update check never delays the initial quota snapshot.

## Interfaces

### Bridge responses

```text
update_status -> {
  installedVersion: string | null,
  latestVersion: string | null,
  updateAvailable: boolean,
  checkedAt: int | null,
  status: "idle" | "checking" | "updating" | "updated" | "failed",
  message: string | null
}

update_check -> same response

update_start { confirmed: true } -> same response with status "updating"
```

The applet treats all fields as untrusted, bounds text, and does not render unknown fields.

## Verification

### Unit and contract tests

- Indicator composition, severity precedence, explicit explanations, and vertical-panel visibility.
- Step segments, range-specific gaps, reset transitions, activity bars, dual axes, exact hover values, and extrema-preserving downsampling.
- SVG QR generation, quiet zone, size bounds, invalid input, dependency absence, and no pairing text embedded as SVG text.
- Version parsing/comparison, fresh Codex cache, stale-cache network refresh, response limits, timeouts, offline fallback, concurrent guards, self-update, installer fallback, and sanitized failures.
- Protocol confirmation and validation for every update action.

### Live visual matrix

The smoke harness exercises and restores synthetic UI states without invoking destructive actions:

- Graph modes `quota`, `activity`, and `both` across `24h`, `7d`, and `30d`.
- Empty, single-point, reset, long-gap, dense, and peak histories.
- Quota unavailable, normal, warning, critical, and stale.
- Reset normal, warning, and six-hour critical.
- Remote disabled, connecting, connected, and errored.
- QR available, manual fallback, claimed, and expired.
- Update current, available, updating, updated, and failed.
- Sessions empty, active, recent, and unavailable.

For every state, assertions cover actor visibility, semantic text, style classes, axis labels, and geometry. Representative screenshots are captured for visual inspection, and Cinnamon journal output is checked for applet errors.

The real Remote daemon remains running throughout the test suite.

## Official Sources

- Codex CLI installation and update guidance: https://developers.openai.com/codex/cli
- Stable `codex update` command: https://developers.openai.com/codex/cli/reference
- Official standalone installer: https://chatgpt.com/codex/install.sh
