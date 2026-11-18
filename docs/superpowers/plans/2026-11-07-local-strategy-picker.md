# Local Strategy Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local bounded strategy comparison with independent rollback, available in both owner panels.
**Architecture:** Reuse verified catalog/import library and Detector JSON jobs; new persistent controller owns isolated resources and a recoverable journal. Separate root guard restores the original before exposing the recommendation.
**Tech Stack:** Existing PHP8, shell platform helpers, static HTML/CSS/JS, React navigation.
**Spec:** docs/superpowers/specs/2026-11-07-local-strategy-picker-design.md

## Global Constraints
Russian/English UI; fixed IPv4/Rustls/timeout8 and hardware-selected concurrency2/4/10, unchanged within a comparison; tests1 once,2+3 warmup+two measurements. Maximum5profiles/60minutes. Preserve exact original config, files, DNS/topology/auth and service state. Never auto-run unknown Lua. No public release or install claims without evidence.

## Review Focus
- Worker death/reboot restores exact original, preserving pre-run OFF.
- Concurrent writes/cancel/apply cannot overwrite foreign changes or another job.
- A bigger total cannot hide TLS/YouTube regression; mismatched/partial reports cannot win.
- AUTO history is isolated/reset identically; original remains byte-identical.
- Signed missing resources/custom Lua are skipped honestly; unsupported architectures refuse safely.

### Task1: Scoring and persistent transaction
Files: public/strategy-picker-core.php, tests/test_strategy_picker.py.
- [x] Add failing tests for metrics, comparable targets, repeated conservative ranking, no TLS/YouTube regression.
- [x] Add failing file-backed transaction tests: normal restore, cancellation, worker death, foreign config conflict, stale apply.
- [x] Implement minimal core and safe journal with unit tests; run relevant import/Detector regression suites.

### Task2: Platform runtime and authenticated API
Files: public/strategy-picker-api.php, public/strategy-picker-runtime.php, public/index.php; experimental/device-profiles helper preflight and package_payload.py.
Interfaces: core score(native)->array, compare(baseline,candidate)->array; runtime status/start/cancel/apply/recover/work/guard.
- [x] Test request validation/CSRF route, limits and guard identity.
- [x] Implement fixed verified catalog selection + library staging; mutable AUTO seeds empty, original unchanged.
- [x] Implement existing Detector jobs orchestration, profile application, service verification, guard and boot recovery.
- [x] Verify real failure/cancel fixtures before router installation.

### Task3: Panel and controlled deployment
Files: public/strategy-picker/{index.html,picker.css,picker.js}, src/components/MainTabs.tsx, docs/LOCAL-STRATEGY-PICKER.md plus EN.
- [x] Verify safe DOM rendering/no innerHTML from reports; cancellation and download in UI tests.
- [x] Add responsive local panel and navigation. Show distinct protocol ratios, phases and reason, explicit apply button.
- [x] Build frontend, run focused regression and package integration checks, independent review.
- [x] Backup both real routers. Stage experimental payload with independent installation rollback; install only verified files and verify browser UI.
- [x] On87U run baseline/candidates/cancel/worker death/recovery; preserve originalOFF after tests. Full six-profile comparison completed; new Instagram goal admission/cancel verified.
- [ ] Repeat on mainASUS, avoid upstream interference; verify originalON/config/resources after completion.
- [ ] Save private deployment and Detector evidence separately; report actual implementation/testing limits.
