# Changelog

## [Unreleased]

### Added

- Added a bounded WebSocket JSON-RPC client for Codex's local Unix control socket, including masked frames, ping/pong, fragmented responses, payload limits, and sanitized failures
- Added explicit Checking, Live, Unavailable, and Unsupported states for connected-device management, with the last successful list retained during temporary failures
- Added real Cinnamon-hosted smoke coverage for Remote pairing status and connected-device inventory without logging device identities or stopping Remote

### Changed

- Widened the dashboard, arranged status alerts across readable rows, and added consistent spacing between content and the scrollbar
- Reduced the outer scrollbar inset while preserving the gutter between the scrollbar and dashboard cards
- Rewrote the project and Cinnamon store READMEs around installation, everyday use, privacy, and troubleshooting
- Replaced the raw `app-server proxy` JSONL attempt with direct local Unix WebSocket transport and daemon-advertised socket discovery
- Added bounded exponential retry for pairing claim checks and disabled stale revocation controls until the device channel recovers

### Fixed

- Removed the duplicated banked-reset count from dashboard status text while keeping the compact count in the panel badge
- Made live layout checks measure the mapped popup so Cinnamon theme allocations are verified accurately
- Fixed connected-device listing and revocation never reaching Codex because the proxy stream was being spoken to with the wrong wire protocol
- Stopped reporting temporary control-channel failures as requiring a newer Codex version

## [1.0.0] - 2026-07-13

### Added

- Stepped quota segments, activity bars, dual percentage/token axes, reset markers, hover values, and explicit graph empty states
- Active/recent Codex sessions with safe default-terminal resume and Open Codex actions
- All, Active, Attention, and Recent session filters with project grouping
- Remote Control pairing status, paired-device inventory, refresh, and confirmed revocation
- A single bounded Python SVG pairing QR path with native Cinnamon rendering and manual-code fallback
- Automatic read-only Codex update discovery and a conditional confirmed background-update action
- Repeatable installed Cinnamon and full dynamic-state live smoke tests, including real pointer travel across the graph
- Shaded uncollected graph history with an explicit local-history start boundary

### Changed

- Centered the compact two-row panel meter and added explicit amber/red/green indicator severity
- Added a dashboard Current indicators row so badge symbols and colors are always explained
- Promoted Remote Control from an experimental dashboard gate to an always-available management section
- Replaced indefinite Remote `Connecting` fallback with verified `Connected` recovery or an honest `Running` state
- Replaced retained installer backups with temporary rollback-only replacement and cleanup
- Bounded history, graph, QR, release-response, and updater work; hardened malformed optional Codex payload handling

### Fixed

- Kept model-specific quota windows out of the canonical 5-hour/weekly history and filtered the already-recorded interleaving pattern without hiding genuine resets
- Kept every graph on its selected 24-hour, 7-day, or 30-day timeline even when local history covers only part of that period
- Corrected graph pointer geometry so hover timestamps and exact values follow the pointer instead of remaining at the newest sample
- Prevented a running but unreadable Remote daemon from being mislabeled as perpetually connecting
- Added labeled, filled quota step trends that show current usage, percentage-point change, collected coverage, and only real reset transitions
- Moved dashboard padding onto the clipped scroll viewport so scrolling cannot leave stale section fragments in the side gutters
- Reserved scrollbar space so it cannot cover dashboard labels or controls
- Ignored callbacks from retired helpers, prevented post-removal bridge restarts, and force-closed unresponsive app-server helpers
- Required explicit confirmation before stopping Remote Control and potentially disconnecting active sessions
- Replaced synchronous Cinnamon bridge writes and shutdown with ordered asynchronous Gio operations
- Removed the downloaded installer-script fallback; updates now use only the installed CLI's fixed `codex update` command
- Added Cinnamon Spices metadata, assets, packaging, and validation support

## [0.1.0] - 2026-07-13

### Added

- Cinnamon panel meter and popup dashboard for Codex usage windows
- Reset countdowns, banked-credit expiry, and confirmed redemption
- Local quota history and quota/activity graph modes
- Optional Codex Remote Control status, start, stop, and pairing controls
- Resilient local app-server bridge with compatibility fallbacks
- Reproducible validation, install, archive, and CI workflows
