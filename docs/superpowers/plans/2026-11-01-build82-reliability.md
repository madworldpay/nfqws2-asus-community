# Build 82 reliability implementation plan

> **For agentic workers:** Use superpowers:executing-plans for each assigned subsystem. Follow systematic debugging and test-driven development. The user has repeatedly requested autonomous implementation without another design-approval round.

**Goal:** Prepare verified fixes for the reported ASUS update, session, catalog and MTProto failures for the next build.

**Architecture:** Keep the existing PHP/React/shell boundaries and signed release/catalog verification. Reproduce each defect before changing behavior. A user report without sufficient evidence remains a documented diagnostic gap rather than a guessed fix.

**Tech Stack:** PHP CGI, React/TypeScript, POSIX shell, BusyBox, Entware, pinned Docker image.

**Spec:** The user's reports in this conversation: AC68U 386.14_2 installation and timer; expired-session message; unavailable signed catalog; update warning flicker without interaction; portable MTProto and the tested AI Board installation.

## Global constraints

- Existing isolation: linked worktree `openwrt-universal-20261025/workspace`, branch `fix/build82-reliability` from public main.
- Do not alter working friend/owner services, LG settings, private credentials, or existing Docker containers.
- Do not erase legitimate operation locks or rewrite opkg status to manufacture success.
- Preserve signed catalog/release verification, origin restrictions and bounded work.
- Do not replace published Build 81 packages or publish Build 82 during preparation.
- Keep user-facing text short, clear and localized; retain community links.
- Respect the user's 3-percent remaining-usage stop threshold.

## Review focus

1. A background status poll must not start installation or report transient lock contention as a failed update.
2. Expired authentication must lead to a usable sign-in flow; never automatically replay a mutation.
3. Legacy ARM/Linux compatibility must be demonstrated against actual ABI/runtime capabilities, not an architecture label alone.
4. Catalog/network errors must remain bounded and distinguishable without weakening TLS/signatures.
5. MTProto readiness requires an actual Telegram response, not just an open local port.

## Task 1: Update state and timer backend investigation

**Files:** existing `source/project/webui/web/public/update-*.php`, `asus/restart-schedule.sh`, corresponding update/timer tests; only modify a path after a reproduced defect.

- [x] Trace the new AC68U logs and passive-warning screenshot against the public Build 81 implementation.
- [x] Add a failing regression for any reproduced contention/state defect, while preserving a genuinely held apply lock.
- [x] Implement the narrow correction; retain strict package-state postflight.
- [x] Run update and timer/reconcile tests, including legacy BusyBox/ARM fixtures where available.
- [x] Report unverified owner-runtime observations separately.

## Task 2: MTProto portability and useful readiness

**Files:** `source/project/webui/web/src/utils/mtproto-install.sh`, `mtprotoInstall.ts`, and `source/project/tests/test_mtproto_install.mjs` as coordinated with the parent.

- [x] Compare the current Python/native installer and pinned Docker app with the reported ARMv5-only binary; verify which report applies to this installer.
- [x] Reproduce command/runtime incompatibilities and the pinned-image entrypoint ignoring Docker Cmd.
- [x] Incorporate a bounded, tested connection path matching the demonstrated WebSocket port-80 success, preserving MTProto end-to-end encryption and existing services.
- [x] Verify generated command/Compose equivalence, correct secret handling and rollback.
- [x] Assert genuine upstream readiness or report that only local readiness was checked; never call the latter a complete functional test.

## Task 3: Catalog transport investigation

**Files:** `source/project/webui/web/public/profile-catalog*.php`, corresponding catalog tests; parent owns shared UI/session code.

- [x] Reproduce available legacy PHP/DNS/TLS failure cases and inspect service availability.
- [x] Fix a proved defect with a failing test first; otherwise prepare a bounded, non-sensitive diagnostic result that distinguishes the failure.
- [x] Preserve exact signed bytes, immutable file hashes, strict HTTPS and origin constraints.
- [x] Run catalog tests plus an independent valid signed-catalog control.

## Task 4: Session recovery, integration and handoff

**Files:** shared frontend authentication/request helpers and affected dialogs/tests; plan/handoff records.

- [x] Trace expired-session handling in timer/catalog/update dialogs and the app's sign-in state.
- [x] Reproduce a session-expired failure and add a regression for recovery without mutation replay or lost user input.
- [x] Implement the minimal shared recovery path and concise messages.
- [x] Integrate independent fixes, run relevant PHP/shell/Node suites and frontend typecheck/build.
- [x] Obtain independent review, then record changes, evidence and remaining gaps for the next build. Do not claim an AC68U hardware fix based only on emulation.

## Scope extension: transactional ASUS updates

The user subsequently requested transparent snapshots/quiesce/install/postflight and restoration of the previous service on failure, with the same ordinary update UI. This additional work is not covered by the completed reliability checkpoint above.

- [ ] Accept healthy persistent policy flags on unrelated installed Entware packages, preserving own held-package and actual unfinished-state gates; reproduce with real ARM opkg.
- [ ] Capture verified old package payload/metadata and settings under the package-manager mutex before stopping services.
- [ ] On failure, reinstall the verified local rollback package through opkg, restore settings and original service intent; surface rollback failure explicitly.
- [ ] Defer SmartDNS transaction resume until the verified final state.
- [ ] Keep shell/bootstrap and panel paths consistent, regenerate embedded closure and ABI launchers.
- [ ] Test install/postflight/rollback failures, killed workers, off-state preservation and both ASUS ABIs; independently review before release.

Evidence: the newly attached 3.72-second video shows Build81 and the pending-packages warning. It does not reveal the actual status rows or whether the warning comes from a historical failed operation. Real opkg has independently demonstrated false-positive rejection of foreign hold/noprune installed rows. No router state was changed during preparation.
