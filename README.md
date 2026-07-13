# Codex Monitor for Cinnamon

Codex Monitor is a Linux Mint Cinnamon panel applet for checking Codex quota usage without opening a terminal. Its compact panel view shows centered 5-hour and weekly meters plus explicit quota, reset, freshness, and Remote Control indicators. The popup adds countdowns, semantic history graphs, recent sessions, banked resets, Remote Control management, and safe Codex update discovery.

## Features

- Dual panel meter and percentages for 5-hour and weekly usage
- Live compact reset countdowns with unavailable windows shown honestly
- 24-hour, 7-day, and 30-day graphs with fitted filled quota trends, percentage-point change, collected-coverage labels, token-activity bars, percentage/token axes, genuine reset markers, and exact hover details
- Banked reset count, expiry, and confirmed one-click redemption
- Amber warning and red critical badges with a plain-language **Current indicators** explanation in the dashboard
- Active and recent Codex sessions that resume in Linux Mint's default terminal
- Open Codex action using `x-terminal-emulator`
- Confirmed Remote Control start, stop, native SVG/manual pairing, device listing, and revocation
- Automatic 12-hour Codex update checks with a button shown only when a newer release is available
- Confirmed background update using `codex update`, with the official standalone installer as a safe fallback
- Theme-integrated Cinnamon popup, keyboard-focusable controls, and vertical-panel fallback
- Local-only quota history with configurable 7–90 day retention, five-minute coalescing, and bounded graph rendering

Codex does not always provide every window or activity method. Missing values appear as unavailable instead of being guessed.

## Requirements

- Linux Mint Cinnamon with Cinnamon 6.0, 6.2, 6.4, or 6.6
- Python 3.10 or newer
- Codex CLI available as `codex` (0.144.3 is the tested baseline)
- Optional `python3-qrcode` package for scannable pairing QR codes; manual pairing remains available without it

The installer does not install or modify system packages.

## Install from this checkout

```sh
sh scripts/install.sh
```

Then open **System Settings → Applets**, find **Codex Monitor**, and add it to a panel. If Cinnamon has cached an older copy, restart Cinnamon with <kbd>Alt</kbd>+<kbd>F2</kbd>, `r`, <kbd>Enter</kbd> on X11, or log out and back in on Wayland.

The installer stages the new copy and keeps the previous copy only long enough to roll back an interrupted replacement. It removes that temporary copy plus legacy retained backups after success, leaving one applet directory. It does not add, remove, or rearrange panel applets automatically.

## Install from the archive

Build the archive with:

```sh
sh scripts/package.sh
```

Extract `dist/codex-monitor@breixopd.zip` into `${XDG_DATA_HOME:-$HOME/.local/share}/cinnamon/applets/` so the final path is:

```text
~/.local/share/cinnamon/applets/codex-monitor@breixopd/metadata.json
```

To uninstall, remove that applet from the panel in System Settings, then delete its directory. The optional graph history is stored separately at `${XDG_DATA_HOME:-$HOME/.local/share}/codex-monitor@breixopd/history.jsonl`.

## Configuration

Right-click the applet and choose **Configure**. Available options cover refresh interval, history retention, graph mode/range, warning thresholds, panel indicators, the Codex executable, and a custom `CODEX_HOME`.

Remote Control is managed directly in the dashboard. Starting it and revoking a paired device require confirmation because paired clients can control Codex on this computer. Pairing uses one QR implementation: the Python bridge creates a bounded SVG and Cinnamon renders it as a native in-memory icon. The manual code remains available if `python3-qrcode` or SVG rendering is unavailable. Pairing data exists only in memory and is cleared when pairing completes or expires.

Update discovery starts only after the first quota snapshot. It reads Codex's fresh local version cache first and otherwise checks the official OpenAI GitHub release endpoint every 12 hours. A current installation shows only its version; **Update Codex…** appears only when a newer stable release is known. Installing always requires confirmation and runs in the background without restarting Cinnamon, Remote Control, the bridge, or existing Codex sessions.

## Privacy and security

The applet starts the official local `codex app-server` process and asks it for account limits. It does not scrape terminal output, read authentication files, copy API keys, or open a network port. Account email is discarded by the bridge and never sent to the UI. The only monitor-originated network request is the bounded release check (and, after explicit update confirmation, retrieval of the official installer fallback).

Only graph samples—capture time, used percentage, and reset time—and non-sensitive update metadata are written to disk. Both history and update state use atomic user-only files with mode `0600`. Token activity, account identity, session previews, paired-client details, pairing codes, installer output, and updater diagnostics are not stored. Reset redemption is confirmed and uses an idempotency key. Session launches and updates use fixed argument arrays rather than a shell pipeline.

See [ADR-001](docs/decisions/001-use-codex-app-server.md) and [ADR-002](docs/decisions/002-local-history-and-remote-control.md) for the design rationale.

## Development

```sh
pytest -q
npm run test:js
python3 scripts/validate.py
sh scripts/package.sh
npm run smoke:live
```

JavaScript model tests run under Node; Cinnamon-specific modules are syntax-checked and then smoke-tested in a real Cinnamon session. Python tests cover response normalization, JSON-RPC behavior, persistence, command validation, terminal launching, updater isolation, reset redemption, and Remote Control. The live smoke command requires the applet to already be enabled on a Cinnamon panel. It exercises every graph mode/range and the empty, single, gap, dense, peak, badge, Remote, pairing, update, and session states; restores real state; captures screenshots under `/tmp/codex-monitor-smoke`; and verifies that the Codex Remote daemon state did not change. Stop behavior is verified only in isolated tests because stopping the live daemon can terminate the active Codex session.

Project layout:

- `files/codex-monitor@breixopd/`: distributable Cinnamon applet
- `helper/codex_bridge/`: local Codex app-server bridge inside the applet package
- `tests/`: Python bridge and pure JavaScript model tests
- `scripts/`: validation, packaging, and local installation

## Compatibility behavior

Codex 0.144.3 is the tested baseline for quota/session monitoring, the Remote daemon, CLI pairing, and self-update. Newer app-server builds add pairing-claim polling and paired-client management methods; Codex Monitor detects those methods independently and labels unavailable controls without disrupting quota monitoring. A monitor-owned app-server can report sessions owned by another Codex process as `notLoaded`; those rows are labeled **Ready to resume**, not falsely reported as active or finished. Unknown quota-window durations are preserved but not mislabeled. Bridge failures leave the last snapshot visible and retry with bounded exponential backoff.

## License

MIT. See [LICENSE](LICENSE).
