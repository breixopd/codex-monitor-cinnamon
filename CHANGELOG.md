# Changelog

## [Unreleased]

## [1.2.2] - 2026-07-16

### Added

- Added keyboard navigation for exact graph timestamps and values, with accessible graph status text
- Added automatic translation-template coverage so new dashboard copy cannot be omitted from the Cinnamon catalog

### Changed

- Keep the last confirmed Remote Control state briefly when a poll fails, showing a clear amber delayed-status warning before falling back to a red error
- Cache normalized quota history and send only the latest 30 days to Cinnamon while retaining up to the configured 90 days on disk
- Reuse unchanged graph and status actors during Remote polling, and inherit theme text colors for readable light and dark Cinnamon themes
- Build deterministic release archives from explicit runtime and store manifests, and pin CI actions and Python tools to immutable versions

### Fixed

- Prevent passive Remote status checks from starting Remote Control, and keep polling after a temporary status failure so the dashboard can recover automatically
- Correlate connected-device responses with the current Remote environment so an older request cannot replace a newer device list
- Persist update ownership across helper restarts, reconcile completion in observing helpers, serialize installs, and protect every state transition from cross-process races
- Reset stale graph hover state when the mode or range changes, wrap long Remote and update labels, and distinguish delayed Remote state from a critical error
- Replace per-refresh quota-history rewrites and reparsing with append-only writes, periodic compaction, and external-change-aware caching

### Security

- Bound all short-lived Codex subprocess output, WebSocket response floods, and retained app-server response and notification queues
- Require same-user, exact-executable, exact-argument matching for passive Remote process detection
- Reject hidden files, backup artifacts, symlinks, and unknown paths from release archives

## [1.2.1] - 2026-07-16

### Fixed

- Recognize sessions running in other local Codex processes even when the monitor's separate read-only app-server reports those threads as not loaded
- Fall back to the verified Codex process start time for elapsed session status when the live process has not yet persisted an in-progress turn state

### Security

- Limit live-session discovery to same-user processes running the exact configured Codex executable, bounded process metadata, canonical thread UUIDs, and open session filenames under the configured `CODEX_HOME`; session files and command lines are never read

## [1.2.0] - 2026-07-16

### Added

- Added a confirmed **Repair Remote** action for the Codex daemon zombie/updater failure, shown only after Codex reports the specific stuck background-service condition
- Added elapsed current-turn time to active, approval-waiting, and user-input-waiting session rows

### Changed

- Recheck Remote Control after an applet-managed Codex update finishes
- Clarified that terminal sessions continue during an update while Remote Control may reconnect
- Added the Python lint gate to CI and bounded bridge messages, local cache reads, history files, and external Codex collections

### Fixed

- Preserved a bounded stuck-daemon error code across the helper bridge instead of reducing every Remote startup failure to the same message
- Made Remote repair fail closed by validating user ownership, managed executable location, executable permissions, zombie state, parent relationship, actual executable identity, and pidfd stability before sending `SIGTERM`
- Removed duplicate Remote Control and banked-reset details from the panel tooltip
- Made dead app-server streams fail promptly, rejected malformed or future graph data, sanitized UI labels, and kept history-write failures from taking quota monitoring offline

## [1.1.1] - 2026-07-15

### Added

- Completed translation coverage for dynamic panel alerts, tooltips, graph states, duration text, session metadata, and update results

### Changed

- Made live Remote probes strictly read-only so validation never starts or stops Remote, creates pairing state, revokes devices, or records device identity
- Pinned CI to the current official Cinnamon Spices validator and added full validation for `dev` branch pushes
- Kept updater failures localizable by mapping bounded helper states to applet-owned messages

### Fixed

- Cleared every Cinnamon timer source identifier during applet removal and removed the retired duplicate pairing action
- Kept dynamic quota, reset, session, Remote, and graph labels fully translatable without concatenating partial sentences
- Removed unused icon assets and tightened helper typing and WebSocket failure handling

## [1.1.0] - 2026-07-14

### Added

- Added a deterministic Cinnamon-rendered store preview with labeled wide, compact, and panel views using only isolated demo actors
- Added active-monitor work-area sizing with compact stacked layouts for narrow and short displays
- Added live wide, compact, and minimum-width layout coverage alongside the existing graph and dynamic-state matrix
- Added a bounded WebSocket JSON-RPC client for Codex's local Unix control socket, including masked frames, ping/pong, fragmented responses, payload limits, and sanitized failures
- Added explicit Checking, Live, Unavailable, and Unsupported states for connected-device management, with the last successful list retained during temporary failures
- Added real Cinnamon-hosted smoke coverage for Remote pairing status and connected-device inventory without logging device identities or stopping Remote

### Changed

- Switched responsive sizing to Cinnamon's current workspace manager and native St scroll-policy constants
- Balanced the Remote Control indicator's optical spacing with the quota and reset indicators
- Kept live smoke coverage data-free by validating geometry and dynamic states without writing full-desktop screenshots
- Kept the 640 px maximum dashboard width while making quota cards, status indicators, filters, actions, device rows, and footer controls responsive below 520 px
- Recalculate dashboard width and scroll height when the menu opens, monitor geometry changes, or panel orientation changes
- Widened the dashboard, arranged status alerts across readable rows, and added consistent spacing between content and the scrollbar
- Compensated for Cinnamon's popup inset so the dashboard has balanced outer margins while preserving the gutter beside the scrollbar
- Rewrote the project and Cinnamon store READMEs around installation, everyday use, privacy, and troubleshooting
- Replaced the raw `app-server proxy` JSONL attempt with direct local Unix WebSocket transport and daemon-advertised socket discovery
- Added bounded exponential retry for pairing claim checks and disabled stale revocation controls until the device channel recovers

### Fixed

- Reduced the excess space below the dashboard footer while retaining top scroll clearance
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
