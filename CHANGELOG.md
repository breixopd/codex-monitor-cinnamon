# Changelog

## [Unreleased]

### Added

- Stepped quota segments, activity bars, dual percentage/token axes, reset markers, hover values, and explicit graph empty states
- Active/recent Codex sessions with safe default-terminal resume and Open Codex actions
- Remote Control pairing status, paired-device inventory, refresh, and confirmed revocation
- A single bounded Python SVG pairing QR path with native Cinnamon rendering and manual-code fallback
- Automatic read-only Codex update discovery and a conditional confirmed background-update action
- Repeatable installed Cinnamon and full dynamic-state live smoke tests

### Changed

- Centered the compact two-row panel meter and added explicit amber/red/green indicator severity
- Added a dashboard Current indicators row so badge symbols and colors are always explained
- Promoted Remote Control from an experimental dashboard gate to an always-available management section
- Replaced retained installer backups with temporary rollback-only replacement and cleanup
- Bounded history, graph, QR, release-response, and updater work; hardened malformed optional Codex payload handling

### Fixed

- Kept model-specific quota windows out of the canonical 5-hour/weekly history and filtered the already-recorded interleaving pattern without hiding genuine resets
- Replaced sparse full-range quota plots with fitted, labeled, filled step trends that show current usage, percentage-point change, collected coverage, and only real reset transitions

## [0.1.0] - 2026-07-13

### Added

- Cinnamon panel meter and popup dashboard for Codex usage windows
- Reset countdowns, banked-credit expiry, and confirmed redemption
- Local quota history and quota/activity graph modes
- Optional Codex Remote Control status, start, stop, and pairing controls
- Resilient local app-server bridge with compatibility fallbacks
- Reproducible validation, install, archive, and CI workflows
