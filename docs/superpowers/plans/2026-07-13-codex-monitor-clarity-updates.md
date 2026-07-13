# Codex Monitor Clarity and Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan. Work inline when the delegation interface cannot select the required low-cost model.

**Goal:** Make Codex Monitor's indicators and graphs self-explanatory, consolidate pairing QR generation, and add safe automatic Codex update discovery with an explicitly confirmed background update.

**Architecture:** Keep presentation-derived state in the applet's JavaScript model, keep privileged/network/process work in the Python bridge, and communicate only through the existing validated JSONL protocol. Extend graph data into semantic stepped quota segments and token bars. Add a thread-safe `UpdateManager` whose public operations are non-blocking snapshots, background checks, and background installs. Generate QR SVG only in Python and pass a bounded string to Cinnamon for native rendering.

**Tech Stack:** Cinnamon JavaScript (GJS/St), Cairo graph drawing, Python 3 standard library, optional `python3-qrcode`, Node's built-in test runner, pytest, shell-based live Cinnamon smoke harness.

## Global Constraints

- Never invoke `remote_stop`, terminate the Remote Control daemon, restart Cinnamon, or stop the current Codex session during implementation or live verification.
- Update discovery is automatic, but update installation requires an explicit click and confirmation.
- Do not run the official installer through a shell pipeline. Download it to a private temporary file and execute `/bin/sh <path>` with a fixed environment.
- Never log, cache, or screenshot pairing secrets.
- Preserve the exact centered two-row panel layout: `5h [bar]` and `W [bar]`, with equal label-to-bar spacing.
- Work in small test-first commits on `feature/codex-monitor-clarity-updates`, then merge locally to `main`; do not push or open a pull request.

---

## Task 1: Normalize panel indicators and explain them in the dashboard

**Files:**

- Modify: `tests/js/model.test.js`
- Modify: `files/codex-monitor@breixopd/model.js`
- Modify: `files/codex-monitor@breixopd/applet.js`
- Modify: `files/codex-monitor@breixopd/ui.js`
- Modify: `files/codex-monitor@breixopd/stylesheet.css`
- Modify: `tests/python/test_applet_source.py`

**Interfaces:**

`panelState(snapshot, settings, now, remoteStatus)` retains its existing scalar fields for compatibility and adds:

```js
indicators: [{
  kind: 'quota' | 'reset' | 'remote' | 'stale',
  severity: 'info' | 'success' | 'warning' | 'critical',
  symbol: string,
  text: string,
}]
```

The UI creates one actor per active panel indicator with classes `codex-indicator`, `codex-indicator-<kind>`, and `codex-indicator-<severity>`. The dashboard header renders the same normalized `text` values below `Current indicators`, or `Usage data current` when the array is empty.

**Steps:**

1. Add failing model tests for quota warning/critical, reset info/warning/final-six-hour critical, Remote connecting/connected/errored, stale state, indicator ordering, and explicit text.
2. Run `node --test tests/js/model.test.js`; confirm the new indicator assertions fail.
3. Implement indicator composition in `model.js`. Quota uses the highest available window; critical takes precedence over warning. Reset uses configured warning hours, with a fixed critical threshold at six hours. Stale and Remote error are critical.
4. Add failing source/UI assertions for per-indicator actors, dashboard `Current indicators`, tooltip/accessibility reuse, and the absence of text badges on vertical panels.
5. Update `applet.js` and `ui.js` to render the normalized indicators without duplicating condition logic. Update CSS so warning is amber, critical red, success green, and info neutral.
6. Run `node --test tests/js/model.test.js` and `pytest -q tests/python/test_applet_source.py`; confirm both pass.
7. Commit: `feat: clarify monitor status indicators`.

## Task 2: Build truthful bounded graph data

**Files:**

- Modify: `tests/js/model.test.js`
- Modify: `files/codex-monitor@breixopd/model.js`

**Interfaces:**

Add these model helpers and export them through `CodexModel`:

```js
quotaSeries(history, windowName, cutoff, now, options = {})
quotaSegments(points, rangeHours)
downsampleQuota(points, maximumPoints = 1200)
graphAxes(series, cutoff, now, rangeHours, mode)
```

Quota points gain `resetTransition: boolean`. `quotaSegments` returns arrays of points; gaps larger than `2h`, `12h`, or `36h` for the `24h`, `7d`, or `30d` ranges start a new segment. Reset transitions remain within a segment so the renderer can draw an intentional vertical step and `R` marker. Activity points retain exact `tokens`; their normalized `value` is rendering-only.

`graphAxes` returns:

```js
{
  x: [{ timestamp, label }],
  left: { kind: 'percent' | 'tokens', maximum, ticks: [{ value, label }] },
  right: null | { kind: 'tokens', maximum, ticks: [{ value, label }] },
}
```

**Steps:**

1. Add failing tests for step semantics, reset detection, all three gap thresholds, empty and single-point input, exact activity token preservation, activity-only token axes, combined dual axes, and hover-distance rejection.
2. Add dense-history tests proving the 1,200-point cap preserves first/last points, reset transitions, and each time bucket's minima and maxima.
3. Run `node --test tests/js/model.test.js`; confirm the new graph tests fail.
4. Implement chronological normalization, reset-transition detection, extrema/reset/endpoints-preserving bucket downsampling, range-specific segmentation, and percent/token axes.
5. Run `node --test tests/js/model.test.js`; confirm all model tests pass.
6. Commit: `feat: model truthful quota and activity graphs`.

## Task 3: Render stepped quota, activity bars, and dual axes

**Files:**

- Modify: `files/codex-monitor@breixopd/graph.js`
- Modify: `files/codex-monitor@breixopd/ui.js`
- Modify: `files/codex-monitor@breixopd/stylesheet.css`
- Modify: `tests/python/test_applet_source.py`
- Modify: `scripts/smoke-live.sh`

**Interfaces:**

`createQuotaGraph()` keeps the current actor contract. `updateQuotaGraph(graph, payload)` accepts:

```js
{
  mode: 'quota' | 'activity' | 'both',
  rangeHours: 24 | 168 | 720,
  cutoff: number,
  now: number,
  series: [{ kind: 'quota' | 'activity', label, color, points, segments? }],
  axes: { x, left, right },
}
```

Quota series render horizontal-then-vertical steps per segment. Activity renders bars whose height uses the token axis. Combined mode draws percentage labels left and token labels right. Reset transitions draw a visible `R`; hover text always reports exact percentage/token values and timestamp.

**Steps:**

1. Add failing source tests that require semantic step, bar, dual-axis, gap-segment, and reset-marker drawing paths rather than a generic line loop.
2. Extend the live smoke harness's synthetic dashboard probe to assert all nine mode/range combinations, left/right axis labels, legends, hover text, empty/single/gap/reset/dense/peak payloads, and bounded graph geometry.
3. Run the source tests and the safe static portion of `scripts/smoke-live.sh`; confirm the new assertions fail without stopping Remote.
4. Refactor `graph.js` into focused axis/grid, quota-step, activity-bar, reset-marker, and hover routines. Update `ui.js` to send the semantic model payload.
5. Style the compact legend and axis labels for legibility at Cinnamon dashboard width.
6. Run `node --test tests/js/model.test.js`, `pytest -q tests/python/test_applet_source.py`, and `sh -n scripts/smoke-live.sh`; confirm they pass.
7. Commit: `feat: render semantic usage graphs`.

## Task 4: Consolidate QR generation into bounded Python SVG

**Files:**

- Modify: `tests/python/test_qr.py`
- Modify: `tests/python/test_remote.py`
- Modify: `tests/python/test_protocol.py`
- Modify: `files/codex-monitor@breixopd/helper/codex_bridge/qr.py`
- Modify: `files/codex-monitor@breixopd/helper/codex_bridge/remote.py`
- Modify: `files/codex-monitor@breixopd/ui.js`
- Modify: `files/codex-monitor@breixopd/applet.js`
- Modify: `scripts/validate.py`
- Modify: `scripts/smoke-live.sh`
- Delete: `files/codex-monitor@breixopd/qr.js`

**Interfaces:**

Replace `encode_qr(value) -> list[list[bool]] | None` with:

```py
encode_qr_svg(value: str, *, qr_factory=None) -> str | None
```

The SVG is at most 256 KiB, contains a four-module quiet zone, uses only a bounded `<svg><rect/><path/></svg>` structure, and contains no `<text>`. Pairing responses expose `qrSvg` instead of `qrMatrix`.

**Steps:**

1. Replace matrix tests with failing tests for SVG structure, four-module quiet zone, output bound, invalid/oversized input, missing dependency fallback, and absence of `<text>` or raw pairing text.
2. Add failing Remote and protocol tests requiring `qrSvg`, with pairing secrets removed after claimed/expired UI states.
3. Run `pytest -q tests/python/test_qr.py tests/python/test_remote.py tests/python/test_protocol.py`; confirm failures.
4. Implement SVG generation with `qrcode.QRCode(border=4)` and compact path output, dependency injection, strict input/output bounds, and XML-safe fixed metadata only.
5. Update Remote normalization and the UI's in-memory native SVG image path. Preserve the manual pairing-code fallback with the explicit message `QR unavailable; use the manual code`.
6. Remove `qr.js`, its imports, validation requirement, Cairo renderer, and live-smoke calls. Add source checks that `qrMatrix` no longer appears in shipped code.
7. Run the targeted Python tests, JS tests, and `python3 scripts/validate.py`; confirm all pass.
8. Commit: `refactor: consolidate pairing qr generation`.

## Task 5: Implement safe automatic update discovery

**Files:**

- Create: `files/codex-monitor@breixopd/helper/codex_bridge/updates.py`
- Create: `tests/python/test_updates.py`
- Modify: `tests/python/test_bridge_entry.py`
- Modify: `files/codex-monitor@breixopd/helper/bridge.py`

**Interfaces:**

```py
class UpdateManager:
    def __init__(self, executable, codex_home, data_dir, *, clock=time.time,
                 urlopen=None, runner=None, thread_factory=None)
    def status(self) -> dict
    def check(self, *, force=False) -> dict
    def start(self) -> dict
```

`status()` never blocks. `check()` starts one daemon worker and immediately returns `status='checking'` unless a successful result is still fresh. `start()` starts one daemon update worker and immediately returns `status='updating'`. State fields match the approved bridge contract exactly.

**Steps:**

1. Add failing tests for numeric version parsing/comparison, installed-version detection, fresh `$CODEX_HOME/version.json`, stale-cache network refresh, fixed user agent, ten-second timeout, one-megabyte response limit, valid `rust-vX.Y.Z` tags, offline last-known fallback, and no update when equal/older.
2. Add failing tests for applet-owned `update-state.json` atomic persistence with mode `0600`, malformed/untrusted cache rejection, and bounded user-facing values.
3. Add failing concurrency tests proving repeated checks return one running worker and an update blocks new checks/updates.
4. Run `pytest -q tests/python/test_updates.py`; confirm failures.
5. Implement `UpdateManager` with an `RLock`, immutable public snapshots, daemon workers, injectable network/process/thread dependencies, and sanitized failures.
6. Wire one manager into `create_runtime` without performing network work during bridge startup. Ensure bridge teardown does not wait on or kill Codex Remote.
7. Run `pytest -q tests/python/test_updates.py tests/python/test_bridge_entry.py`; confirm all pass.
8. Commit: `feat: add background codex update discovery`.

## Task 6: Implement confirmed background update execution and protocol

**Files:**

- Modify: `tests/python/test_updates.py`
- Modify: `tests/python/test_protocol.py`
- Modify: `tests/python/test_service.py`
- Modify: `files/codex-monitor@breixopd/helper/codex_bridge/updates.py`
- Modify: `files/codex-monitor@breixopd/helper/codex_bridge/protocol.py`
- Modify: `files/codex-monitor@breixopd/helper/codex_bridge/service.py`

**Interfaces:**

Add service methods `update_status()`, `update_check(force=False)`, and `update_start()`. Add validated actions:

```text
update_status params={}
update_check params={} or {force: boolean}
update_start params={confirmed: true}
```

The updater first executes `[resolved_codex_path, 'update']` with `shell=False`. Only when output/exit status identifies self-update as unavailable does it download `https://chatgpt.com/codex/install.sh` with the same response bounds into a mode-`0600` temporary file and execute `['/bin/sh', path]` with `CODEX_NON_INTERACTIVE=true`. It bounds captured output and exposes only fixed sanitized messages.

**Steps:**

1. Add failing update tests for successful self-update, unsupported self-update fallback, installer download/permissions/execution, timeouts, nonzero exits, post-update version re-read, and no raw stdout/stderr in public state.
2. Add failing protocol/service tests for all three actions, exact parameter validation, explicit confirmation, and manager-unavailable errors.
3. Run `pytest -q tests/python/test_updates.py tests/python/test_protocol.py tests/python/test_service.py`; confirm failures.
4. Implement the self-update and fallback state machine. Clean up temporary files in `finally`; do not invoke shell pipelines or any Remote action.
5. Wire service and protocol operations. Treat unknown parameters as invalid, including unconfirmed update starts.
6. Run the targeted Python tests; confirm all pass.
7. Commit: `feat: support confirmed background codex updates`.

## Task 7: Add automatic polling and conditional update UI

**Files:**

- Modify: `tests/js/model.test.js`
- Modify: `tests/python/test_applet_source.py`
- Modify: `files/codex-monitor@breixopd/model.js`
- Modify: `files/codex-monitor@breixopd/applet.js`
- Modify: `files/codex-monitor@breixopd/ui.js`
- Modify: `files/codex-monitor@breixopd/stylesheet.css`

**Interfaces:**

Add `normalizeUpdateState(value)` to `model.js`, returning only bounded known fields and one of `idle`, `checking`, `updating`, `updated`, or `failed`.

The applet requests `update_status` after its first quota snapshot, triggers `update_check` when no fresh check is available, polls active checks/updates without delaying normal refresh, and repeats discovery every twelve hours. The dashboard footer states are:

- current: `Codex X`
- available: `Codex X → Y` plus `Update Codex…`
- updating: `Updating Codex…`, disabled
- updated: `Updated to Codex X. New Codex launches use this version.`
- failed: `Update failed; Codex X is still installed` plus `Retry`

**Steps:**

1. Add failing model tests for rejecting unknown states, overlong/untrusted strings, invalid timestamps, and inconsistent `updateAvailable` combinations.
2. Add failing source tests for post-snapshot startup check, twelve-hour cadence, active-state polling, conditional button visibility, confirmation dialog, and no update panel badge.
3. Run JS and source tests; confirm failures.
4. Implement normalized update state, independent timers, bridge callbacks, and teardown cleanup. Keep normal snapshot/session/Remote refresh operational while update workers run.
5. Implement the dashboard footer and confirmation dialog. Only send `update_start` after confirmation; never infer consent from update availability.
6. Run `node --test tests/js/model.test.js` and `pytest -q tests/python/test_applet_source.py`; confirm all pass.
7. Commit: `feat: surface safe codex updates in dashboard`.

## Task 8: Complete the dynamic visual matrix and product documentation

**Files:**

- Modify: `scripts/smoke-live.sh`
- Modify: `scripts/smoke_bridge.py`
- Modify: `tests/python/test_smoke_bridge.py`
- Modify: `scripts/validate.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/decisions/002-local-history-and-remote-control.md`
- Modify: `dist/codex-monitor@breixopd.zip`

**Steps:**

1. Add failing bridge-smoke assertions for the update status/check contract and SVG pairing contract; do not call `update_start` or `remote_stop` in smoke tests.
2. Expand the live synthetic-state matrix to cover every graph mode/range, graph edge case, indicator severity, reset expiry band, Remote state, QR state, update state, and session state from the approved design.
3. Add representative screenshot capture with secret-free synthetic QR content, actor visibility/text/style/axis/geometry assertions, and Cinnamon journal error checks. Save screenshots only under `/tmp` and remove them after inspection.
4. Run `pytest -q tests/python/test_smoke_bridge.py` and static validation; confirm failures before the harness changes and passes afterward.
5. Update README/CHANGELOG/ADR with badge meanings, graph semantics, optional `python3-qrcode`, automatic read-only update checks, explicit install confirmation, and the Remote non-disruption guarantee.
6. Run the full safe verification set:

```sh
pytest -q
npm run test:js
npm run check
npm run package
git diff --check
```

7. Install the freshly packaged applet with the repository installer, which first removes all old installed copies/backups, then reload the single enabled instance without stopping Remote.
8. Run `npm run smoke:live`, inspect representative screenshots directly, and check `journalctl --user -b --since '10 minutes ago'` for Codex Monitor/Cinnamon errors. Verify the Remote status before and after is unchanged and running.
9. Commit: `test: cover codex monitor dynamic states`.

## Task 9: Review, merge locally, and verify the final state

**Files:** All changed files in the feature branch.

**Steps:**

1. Review the branch diff for correctness, security, unnecessary complexity, stale QR/update code, secret handling, and accidental Remote lifecycle calls. Fix findings test-first and commit them separately.
2. Re-run the full suite and live smoke after review fixes. Confirm exactly one installed applet copy and no obsolete menu versions/backups.
3. Confirm `git status --short`, commit history, and package contents are clean and intentional.
4. Merge `feature/codex-monitor-clarity-updates` into local `main` with a non-fast-forward merge, without pushing or creating a pull request.
5. On `main`, re-run `npm run check`, `npm test`, package validation, and a non-destructive live status probe. Confirm Remote is still running.
6. Delete the local feature branch and report the feature overview, test evidence, installed state, merge commit, and any environmental limitations.
