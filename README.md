# Codex Monitor for Cinnamon

Codex Monitor is a Linux Mint Cinnamon panel applet for checking Codex quota usage without opening a terminal. Its compact panel view shows centered 5-hour and weekly meters plus actionable reset, freshness, and Remote Control states. The popup adds countdowns, detailed history, recent sessions, banked resets, and complete Remote Control management.

## Features

- Dual panel meter and percentages for 5-hour and weekly usage
- Exact reset time plus a live compact countdown
- 24-hour, 7-day, and 30-day quota/activity graphs with axes, legend statistics, reset markers, and hover details
- Banked reset count, expiry, and confirmed one-click redemption
- Visual warning, critical, expiring-credit, stale, and Remote Control states
- Active and recent Codex sessions that resume in Linux Mint's default terminal
- Open Codex action using `x-terminal-emulator`
- Confirmed Remote Control start, stop, pairing, device listing, and revocation
- Theme-integrated Cinnamon popup, keyboard-focusable controls, and vertical-panel fallback
- Local-only quota history with configurable 7–90 day retention

Codex does not always provide every window or activity method. Missing values appear as unavailable instead of being guessed.

## Requirements

- Linux Mint Cinnamon with Cinnamon 6.0, 6.2, 6.4, or 6.6
- Python 3.10 or newer
- Codex CLI available as `codex` (0.144.3 is the tested full-feature baseline)

No Python or JavaScript runtime dependencies are installed by the applet.

## Install from this checkout

```sh
sh scripts/install.sh
```

Then open **System Settings → Applets**, find **Codex Monitor**, and add it to a panel. If Cinnamon has cached an older copy, restart Cinnamon with <kbd>Alt</kbd>+<kbd>F2</kbd>, `r`, <kbd>Enter</kbd> on X11, or log out and back in on Wayland.

The installer preserves an existing installation under `${XDG_DATA_HOME:-$HOME/.local/share}/codex-monitor@breixopd/install-backups/`. Backups stay outside Cinnamon's applet-discovery directory, and stale sibling backups from older development installs are removed. The installer does not add, remove, or rearrange panel applets automatically.

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

Right-click the applet and choose **Configure**, or use the Settings button in its popup. Available options cover refresh interval, history retention, graph mode/range, warning thresholds, panel indicators, the Codex executable, and a custom `CODEX_HOME`.

Remote Control is managed directly in the dashboard. Starting it and revoking a paired device require confirmation because paired clients can control Codex on this computer. Pairing codes are shown only in the popup and are not persisted by Codex Monitor. Codex CLI 0.144.3 still labels its underlying `remote-control` command experimental; the applet therefore reports unsupported methods without disrupting quota monitoring.

## Privacy and security

The applet starts the official local `codex app-server` process and asks it for account limits. It does not scrape terminal output, read authentication files, copy API keys, or open a network port. Account email is discarded by the bridge and never sent to the UI.

Only graph samples—capture time, used percentage, and reset time—are written to disk. The file is replaced atomically with user-only mode `0600`. Token activity, account identity, session previews, paired-client details, and pairing codes are not stored. Reset redemption is confirmed and uses an idempotency key. Session launches validate the thread UUID and use fixed argument arrays rather than a shell.

See [ADR-001](docs/decisions/001-use-codex-app-server.md) and [ADR-002](docs/decisions/002-local-history-and-remote-control.md) for the design rationale.

## Development

```sh
pytest -q
npm run test:js
python3 scripts/validate.py
sh scripts/package.sh
npm run smoke:live
```

JavaScript model tests run under Node; Cinnamon-specific modules are syntax-checked and then smoke-tested in a real Cinnamon session. Python tests cover response normalization, JSON-RPC behavior, persistence, command validation, terminal launching, installer isolation, reset redemption, and the full Remote Control lifecycle. The live smoke command requires the applet to already be enabled on a Cinnamon panel; it reloads the installed source, captures screenshots under `/tmp/codex-monitor-smoke`, and leaves the Codex Remote daemon running because stopping it can terminate the active Codex session. Stop behavior is verified in isolated tests.

Project layout:

- `files/codex-monitor@breixopd/`: distributable Cinnamon applet
- `helper/codex_bridge/`: local Codex app-server bridge inside the applet package
- `tests/`: Python bridge and pure JavaScript model tests
- `scripts/`: validation, packaging, and local installation

## Compatibility behavior

Codex 0.144.3 is the tested baseline for quota/session monitoring, the Remote daemon, and CLI pairing. Newer app-server builds add pairing-claim polling and paired-client management methods; Codex Monitor detects those methods independently and labels unavailable controls without calling the whole Remote feature experimental or disrupting quota monitoring. A monitor-owned app-server can report sessions owned by another Codex process as `notLoaded`; those rows are labeled **Ready to resume**, not falsely reported as active or finished. Unknown quota-window durations are preserved but not mislabeled. Bridge failures leave the last snapshot visible and retry with bounded exponential backoff.

## License

MIT. See [LICENSE](LICENSE).
