# Restart controls implementation plan

> **For agentic workers:** use superpowers:executing-plans or subagent-driven-development. Keep export diagnosis independent of restart controls.

**Goal:** let users restart only NFQWS2 manually, periodically, or after a process exit, with explicit opt-in and no restart loop.

**Architecture:** use existing authenticated service actions, a compact header timer dialog, and platform lifecycle locks. Persist the interval and watchdog choice separately from strategy text; keep transient countdown and attempts in RAM. ASUS uses its existing reconcile job; native OpenWrt uses one minute cron supervision and removes conflicting unconditional procd respawn.

**Tech stack:** existing React/MUI RU/EN panel, PHP API, POSIX shell with pinned BusyBox and existing platform schedulers.

**User requirements:** visible restart icon; timer icon with tooltip; 4/12/24 hours or a custom interval; short description “Для устройств с небольшим объёмом ОЗУ”; optional watchdog; anti-loop details in a tooltip. The user has requested direct implementation without repeated design questions.

## Global constraints

- Both automatic features default OFF. Integer custom interval 1–168 hours is the implementation choice; validate on both sides.
- Manual stop has priority; no automatic path may turn a manually stopped service back on.
- Only NFQWS2 core restarts. Preserve panel, router, DNS, MTProto and existing services.
- Respect package/update/import/core leases. An active update defers automation.
- Watchdog waits 1, 5 and 15 minutes before at most three attempts, then latches. Interval edits and successful short starts do not clear the failure budget. Explicit manual start/restart or watchdog OFF/ON rearms it.
- Missing WAN during initial requested start must not be mistaken for a crash.
- No live installation or new release before scoped runtime/API/browser tests and independent review.

## Review focus

- Manual stop races with a pending automatic attempt: recheck running intent under the lifecycle mutex.
- Repeated immediate process exits: the timer cannot bypass the watchdog latch.
- Clock jumps and reboot: use uptime and boot identity rather than wall clock for countdown.
- Existing procd respawn: one supervisor owns restart policy.
- Failed save or stale browser session: preserve the draft and never silently enable automation.

## Tasks

- [ ] Backend: write RED shell/PHP/HTTP tests; implement validated config/API plus scheduler capability checks; verify GREEN.
- [ ] Runtime: write RED tests for both platforms, manual-stop protection, crash budgets, initial WAN wait, overlaps and update locks; implement lifecycle integration and packaging; verify GREEN.
- [ ] Frontend: write RED real-browser RU/EN tests; implement manual icon, timer dialog and explicit-save settings; verify GREEN and mobile layout; capture screenshots.
- [ ] Integration: review the combined diff, run affected lifecycle/package/update/browser checks, verify safe private fixtures on available ASUS, and produce a reviewable build after resolving blockers.

Export Build80 diagnosis continues separately. An unconfirmed delivery does not itself prove rejection or loss; do not label the incident fixed without boundary evidence. The previous-package automatic rollback proposal is also separate from the completed update-check recovery fix.
