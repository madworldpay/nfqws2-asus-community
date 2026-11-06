# Detector result context implementation plan

> **For agentic workers:** Use superpowers:executing-plans or the explicitly scoped parallel tasks below. Prove each behavior with RED then GREEN; do not publish before integration review.

**Goal:** Explain native results and add truthful HTTP control checks with downloadable service/strategy context.

**Architecture:** Preserve the original terminal. Add a fixed-target, bounded backend endpoint and an independent frontend view. Native historical TXT context stays unknown.

**Tech stack:** PHP, bounded verified TLS sockets, React/MUI/TypeScript, existing browser/PHP tests and all22 package builders.

**Spec:** `docs/superpowers/specs/2026-11-06-dpi-result-context-design.md`.

## Global constraints

Keep original native verdicts/reports, authentication and idle gates; no DNS/service/strategy changes. Fixed public targets, verified TLS, pinned public IPv4, no redirects/proxy/cookies,10s wall deadline and256KiB body cap. Reply exactly as specified; record actual control-request context, never invent native-run context. All platforms/architectures and owner deployment are required.

## Review focus

- A completed HTTP400 must remain distinguishable from successful content delivery.
- DNS poisoning/private answers and redirects must not reach internal services.
- Late child output/unmount/repeated clicks must not duplicate work or overwrite another run.
- Config changes and old native reports must not be labeled as stable/known test context.
- Original terminal stays one instance and mobile retains full scrolling.

## Task1: Backend control probe

Files: new `source/project/webui/web/public/dpi-site-check.php`, optional private helper under `source/project/asus/dpi/`, new `source/project/tests/test_dpi_site_check.py`.

Interface: `AsusDpiSiteCheck::validate(array $post):void`, `AsusDpiSiteCheck::check(string $target):array`; trusted constructor-only dependencies may enable fixtures. Root integrates index dispatch and packaging after review. Do not change shared frontend/version/release files.

- [x] Write and run RED behavior tests for the spec's response, gates, safety and deadline.
- [x] Implement minimal bounded probe and pure-data context capture; run GREEN tests.
- [x] Report exact changed files, observed RED/GREEN evidence and remaining limitations.

## Task2: Frontend view and download

Files: new `DpiSiteCheck.tsx`, `dpiSiteCheckClient.ts`, download utility/tests; modify `DpiTerminalDialog.tsx`, RU/EN translations; meaningful actual-React browser regression.

Interface: endpoint/reply in spec; component receives csrfToken. Use unique stable React keys. Root integrates backend before live verification. Do not change backend/version/release files or rebuild dist.

- [x] Write and run RED tests for HTTP400, validation, download/context and original-terminal lifecycle.
- [x] Implement service selection, sequential checks, accurate labels and TXT download.
- [x] Verify mobile, RU/EN, close/reopen and no duplicate terminal/request.

## Task3: Integration, review, release and owner verification

- [x] Integrate authenticated index route and all packaging/platform paths; add meaningful API/payload tests.
- [x] Update help/GitHub docs, pending notes, version as a new build; never replace95.
- [x] Run appropriate PHP/browser/type/lint/build checks and independent whole-change review; address consequential findings with regression evidence.
- [ ] Build/reproduce all22, scan source for private material, verify signatures/assets; publish using checked madworldpay account.
- [ ] Back up owner settings/resources, deploy through ordinary panel updater once, verify actual packages/panels, preserved hashes and previous ASUS ON/OpenWrt OFF states. Close temporary task connections/tabs.
- [ ] Save live screenshot and concise outcome with exact limits; record anything prepared but not deployed.
