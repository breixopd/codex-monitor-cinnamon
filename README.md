# Codex Monitor for Cinnamon

Codex Monitor is a Linux Mint Cinnamon panel applet for checking Codex quota usage without opening a terminal. Its compact panel view shows centered 5-hour and weekly meters plus explicit quota, reset, freshness, and Remote Control indicators. The popup adds countdowns, semantic history graphs, recent sessions, banked resets, Remote Control management, and safe Codex update discovery.

## Features

- Dual panel meter and percentages for 5-hour and weekly usage
- Live compact reset countdowns with unavailable windows shown honestly
- 24-hour, 7-day, and 30-day graphs with fixed selected ranges, visibly shaded uncollected history, quota trends, token activity, reset markers, and exact pointer hover details
- Banked reset count, expiry, and confirmed one-click redemption
- Amber warning and red critical badges with a plain-language **Current indicators** explanation in the dashboard
- Filterable Codex sessions grouped by project, with focused Active, Attention, and Recent views
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

Remote Control is managed directly in the dashboard. Starting it and revoking a paired device require confirmation because paired clients can control Codex on this computer. The applet confirms an existing Linux Remote process before probing its connection, so it does not silently enable Remote. Pairing uses one bounded SVG implementation with a manual-code fallback.

Update discovery starts only after the first quota snapshot. It reads Codex's fresh local version cache first and otherwise checks the official OpenAI GitHub release endpoint every 12 hours. A current installation shows only its version; **Update Codex…** appears only when a newer stable release is known. Installing always requires confirmation and runs in the background without restarting Cinnamon, Remote Control, the bridge, or existing Codex sessions.

## Privacy and security

The applet uses the official local `codex app-server`. It does not scrape terminal output, read authentication files, copy API keys, or open a network port. Only bounded quota-history samples and non-sensitive update metadata are stored, in user-only files. Pairing codes, account identity, session previews, device details, and updater output remain ephemeral.

## Development

```sh
npm test
npm run check
npm run package
npm run smoke:live
```

The live smoke command requires the applet to be enabled on a Cinnamon panel. It restores the user’s graph/filter state and never stops the live Remote daemon.

## License

MIT. See [LICENSE](LICENSE).
