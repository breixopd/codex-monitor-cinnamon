# Codex Monitor for Cinnamon

Codex Monitor is a Linux Mint Cinnamon panel applet for checking Codex quota usage without opening a terminal. Its compact panel view shows the 5-hour and weekly windows; the popup adds countdowns, local history, token activity when available, banked reset credits, and opt-in Remote Control management.

## Features

- Dual panel meter and percentages for 5-hour and weekly usage
- Exact reset time plus a live compact countdown
- 24-hour, 7-day, and 30-day quota/activity graphs
- Banked reset count, expiry, and confirmed one-click redemption
- Visual warning, critical, expiring-credit, stale, and Remote Control states
- Optional confirmed start/stop/pair controls for Codex Remote Control
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

The installer preserves an existing installation as a timestamped sibling backup. It does not add, remove, or rearrange panel applets automatically.

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

Right-click the applet and choose **Configure**, or use the Settings button in its popup. Available options cover refresh interval, history retention, graph mode/range, warning thresholds, reset badges, the Codex executable, a custom `CODEX_HOME`, and the experimental Remote Control section.

Remote Control is off by default. Starting it requires confirmation because paired mobile clients can control Codex on this computer. Pairing codes are shown only in the popup and are not persisted by Codex Monitor.

## Privacy and security

The applet starts the official local `codex app-server` process and asks it for account limits. It does not scrape terminal output, read authentication files, copy API keys, or open a network port. Account email is discarded by the bridge and never sent to the UI.

Only graph samples—capture time, used percentage, and reset time—are written to disk. The file is replaced atomically with user-only mode `0600`. Token activity, account identity, and pairing codes are not stored. Reset redemption is confirmed and uses an idempotency key. Child commands use argument arrays rather than a shell.

See [ADR-001](docs/decisions/001-use-codex-app-server.md) and [ADR-002](docs/decisions/002-local-history-and-remote-control.md) for the design rationale.

## Development

```sh
pytest -q
npm run test:js
python3 scripts/validate.py
sh scripts/package.sh
```

JavaScript model tests run under Node; Cinnamon-specific modules are syntax-checked and then smoke-tested in a real Cinnamon session. Python tests cover response normalization, JSON-RPC behavior, persistence, command validation, reset redemption, and Remote Control wrappers.

Project layout:

- `files/codex-monitor@breixopd/`: distributable Cinnamon applet
- `helper/codex_bridge/`: local Codex app-server bridge inside the applet package
- `tests/`: Python bridge and pure JavaScript model tests
- `scripts/`: validation, packaging, and local installation

## Compatibility behavior

Codex 0.144.3 supports the full baseline used by this release. When `account/usage/read` is unavailable, activity graphs are empty while quota monitoring continues. Unknown quota-window durations are preserved by the bridge but are not mislabeled as 5-hour or weekly windows. Bridge failures leave the last snapshot visible and retry with bounded exponential backoff.

## License

MIT. See [LICENSE](LICENSE).
