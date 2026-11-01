# ASUS configure recovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans. The human already requested autonomous implementation; do not request another design discussion.

**Goal:** Let the ordinary updater safely finish an interrupted NFQWS2 ASUS configuration while preserving active settings and stopped/running intent.

**Architecture:** Keep normal installed-package validation strict. Add an explicit configure action for one own unpacked row matching the verified release, then use the existing detached staged worker, settings backup, process authorization and opkg POSIX mutex. A bootstrap bridge must use the same validation, rather than an unguarded shell `opkg configure` shortcut.

**Tech stack:** BusyBox ash, PHP 8, syscall-only ARM/AArch64 launcher, Python process tests.

**Known evidence:** Build 80 on AC68U was `install user unpacked`; its installed postinst matched the published Build 80 bytes; core and web were running. The original installation output is unavailable. A controlled own-only configure completed without changing the configuration hash. This proves the immediate recovery obstruction, not the original reason configuration was interrupted.

## Global constraints

- No live router writes/restarts, package DB edits, force installation, configure-all, commits, push or release publication in this task.
- Other pending packages, active update leases, changed postinst, wrong pending version and unconsumed migration snapshots block recovery before stopping services.
- Configure always runs with `NFQWS_ASUS_NO_START=1`; restore original lifecycle intent only after healthy exact-version status and settings verification.
- Preserve transaction logs and snapshot on failure/interruption. Do not claim complete old-binary rollback.

## Review focus

- Package manager configure can process foreign unpacked rows even with an own package argument: inspect again under its POSIX mutex.
- Installed immutable maintainer script must equal the verified archive; a version string alone does not prove recovery safety.
- Migration restore can replay an old snapshot over later edits: refuse recovery until an existing data-restored/complete marker proves it was consumed.
- A stopped core must never briefly start in postinst.
- SSH/client death must leave the detached transaction alive and its diagnostics retained.

### Task 1: Validate explicit configure candidates

Files: `update-manifest.php`, `update-package.php`, `update-prepare.php`; tests `test_package_update_prepare.py`, `test_package_update_manifest.py`.

- [x] Add failing behavioral tests for own verified same-version configure, foreign pending row, wrong pending version, changed/symlinked postinst and unconsumed migration snapshot.
- [x] Run new tests and confirm expected failures: existing database rejects own unpacked before inspecting recovery proof.
- [x] Add opt-in own-unpacked database inspection and explicit candidate action; normal inspection stays strict.
- [x] Verify fixed installed postinst path against archive bytes and block unconsumed migration snapshot.
- [x] Recheck recovery proof during preparation, worker validation and final locked preflight.

### Task 2: Use existing locked worker

Files: `asus/update/opkg-launch.c`, launcher outputs/record, `update-worker.php`; tests `test_package_update_opkg_lock.py`, `test_package_update_apply.py`.

- [x] Add and run failing real-process test for the literal configure action.
- [x] Accept only an optional literal `configure`, execute `opkg configure nfqws2-asus` in the same mutex-owning PID and pass NO_START.
- [x] Keep final preflight bound to the worker's validated action; reject attempts to select another action.
- [x] Test stopped/running/waiting intent, foreign pending race, script mutation race, opkg contention and unsuccessful postflight.
- [x] Rebuild deterministic ARM/AArch64 launchers and run existing QEMU mutex tests.

### Task 3: Bootstrap bridge and diagnostics

- [x] Reuse shared verification/worker code in a standalone generated bridge usable even when installed Build 80 rejects unpacked.
- [x] Stage only trusted local installer closure/verified archive bytes; keep fixed release endpoints and normal package identity gates.
- [x] Detach before package mutation; retain job log, pid, terminal status and private settings snapshot on interruption/failure.
- [x] Verify SSH/HUP/client-death behavior with real child processes, plus safe retry and concurrent install refusal.

### Task 4: User status and final verification

- [x] Give explicit recovery status and actionable bounded failure code without shell-command workarounds.
- [x] Run package update suites and installer suites, both host ash and BusyBox ash; report every failure/skip.
- [x] Regenerate native installer bundle after shared package/manifest modules change.
- [x] Obtain independent review from the parent before committing/publishing.

## Verified outcome

189 updater tests passed (five root-only receiver skips), 49 installer tests each under dash and BusyBox ash, real signed Build 80 artifacts across all three ASUS ABI cases with 16 MiB PHP, ARM 2.6 runtime and QEMU mutex checks passed. Independent review found no blocker under the conservative failure contract. The original first installation interruption is not proven.

A failed staged upgrade may leave the core stopped; a later retry preserves the current observed state rather than guessing permission from old job history. There is no full previous-binary rollback.
