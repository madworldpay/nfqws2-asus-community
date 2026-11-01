# Optional IP Health sockets preparation implementation plan

> **For agentic workers:** Use superpowers:executing-plans with RED → GREEN verification. Parent has approved this bounded design and inline execution; do not commit or deploy.

**Goal:** Make the fixed sockets capability available after explicit IP Health enable without breaking the released Build81 one-click updater or upgrading foreign PHP packages.

**Architecture:** ASUS Depends and manifest v1 remain unchanged. A root-only detached capability worker consumes the closed, signed own-payload catalog and inert official IPKs. It holds the shared updater mutation lease and its private operation lease; a sockets-only syscall launcher holds the actual POSIX opkg mutex continuously from final preflight through `exec(opkg)`.

**Tech stack:** PHP8.2+, BusyBox, freestanding Linux C, actual Entware opkg, Python unittest/QEMU.

**Spec:** Parent-approved contract, recorded in this task; Build82 handoff compatibility constraint.

## Global constraints

- No live writes, commits, releases or unrelated package upgrades.
- Never change existing ASUS Depends or weaken the normal updater's strict pending/Depends rules.
- Only exact catalog PHP package/runtime version and architecture are supported. Existing installed sockets are probed and reused, never upgraded.
- Install only absent fixed files with `--nodeps`; no force flags or status DB edits.
- Resume only an exact unpacked target proven by this generation's private native-boundary journal and exact catalog payload/metadata, with unchanged foreign records.
- No core stop/start; disabled feature is inert. Failed/pending capability remains unavailable and visible.

## Review focus

- Existing incompatible sockets or owner-created file: refuse without touching it.
- Real foreign pending/hold policies: healthy holds accepted, true pending refused.
- Interruption after unpack: exact owned proof permits only own configure; missing/tampered proof refuses.
- PHP API mismatch may exit0: strict probe sentinel and empty diagnostic output required.
- Native and shared mutex contention, stalled subprocesses, symlinks and catalog/archive mutation: bounded failure before opkg.

### Task1: Policy and native boundary

Files: new `webui/web/public/ip-health-sockets.php`; modify `asus/update/opkg-launch.c`, `build-launchers.py`; new policy and native-launcher tests.
Interface: `NfqwsIpHealthSockets(array $trustedOptions=[])->prepare(): array`, `preflight(string $id,string $action): void`, `apply(string $id): array`, `status(): array`. Catalog schema_version1 entries bind ABI, php_package_version, php_version, official artifact and exact two payload files.

- [x] Add failing tests for real official archive validation and private-root real manager installation, immutable foreign records, strict negative policy, ownership-bound resume.
- [x] Add failing native tests proving sockets-only configure and rejection of rollback/force actions while preserving the POSIX lock.
- [x] Implement minimal policy and compile-time sockets-only variant, regenerate both inventories/binaries.
- [x] Run focused policy/native tests and existing native regression on host/ARM/AArch64.

### Task2: Detached fixed worker integration

Files: new `asus/ip-health-sockets/{worker.php,control.sh}`. Builder/runtime agent owns payload list and feature-enable trigger.
Interface: `control.sh queue|status`; root worker `run|status|preflight ID install|configure`. Queue is detached through the bundled BusyBox; run waits at most60s for updater lease, then loads the current policy, retries only the sealed operation, and records a closed capability result. No network/feed resolution or ordinary boot activity.

- [x] Add failing process tests for disabled no-op, native/shared lease contention, bounded apply/probe timeout and failure output.
- [x] Implement fixed entry and expose `{state,code}` status without auto-retry on reads.
- [x] Run full relevant component suite, independent review, and report verified scope/limitations.

## Verified checkpoint

The ASUS package dependency list and release manifest v1 are unchanged. The inert catalog/IPKs and runtime trigger integration belong to the builder/API agents; this task provides the guarded policy, fixed detached worker and dedicated native launcher.

- Policy19 cases pass on host PHP8.5 and actual ARM32 Entware PHP8.2 with16MiB limit. All3 official artifacts install through real private-root Entware opkg and load in their matching actual PHP CGI.
- Full IP Health93 cases pass, with one isolated native-nft container fixture skipped. Full existing updater227 pass, with five unavailable frozen relay fixtures skipped.
- Native sockets-only mutex10 cases pass on host, ARMv7 and AArch64. Both normal and capability binaries/inventories reproduce byte-for-byte.
- Independent policy review identified modern official Provides compatibility; exact whitelist and both modern artifact regressions close it. No remaining policy finding.
- Interrupted module-unpacked coverage uses real manager payload/metadata followed by an explicit persisted-state fixture; the hook-free official module normally configures immediately. This is not a claim of reproduced power-loss timing or live router proof.
- Unsupported PHP/ABI, unproved pending ownership, unsafe paths or changed foreign records remain explicit capability failure. No foreign upgrade, database rewrite, core start/stop or live router mutation was performed.
