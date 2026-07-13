# Changelog

## [Unreleased]

### Added

- Detailed graph axes, legend statistics, reset markers, hover values, and empty states
- Active/recent Codex sessions with safe default-terminal resume and Open Codex actions
- Remote Control pairing status, paired-device inventory, refresh, and confirmed revocation
- In-memory pairing QR with the manual code retained as a fallback
- Repeatable installed Cinnamon and live bridge smoke tests

### Changed

- Centered the compact two-row panel meter and made reset, stale, and Remote states dynamic
- Promoted Remote Control from an experimental dashboard gate to an always-available management section
- Replaced retained installer backups with temporary rollback-only replacement and cleanup

## [0.1.0] - 2026-07-13

### Added

- Cinnamon panel meter and popup dashboard for Codex usage windows
- Reset countdowns, banked-credit expiry, and confirmed redemption
- Local quota history and quota/activity graph modes
- Optional Codex Remote Control status, start, stop, and pairing controls
- Resilient local app-server bridge with compatibility fallbacks
- Reproducible validation, install, archive, and CI workflows
