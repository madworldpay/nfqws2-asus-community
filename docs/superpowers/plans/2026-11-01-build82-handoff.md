# Build 82 preparation checkpoint

Branch: `fix/build82-reliability`. Public main remains unchanged; Build82 has not been published. The sections below describe the initial checkpoint. The owner's authorized hardware checks and subsequent findings are recorded at the end.

## Preserved commits

- `7190d77`: session recovery, catalog diagnostics/races, MTProto real-response readiness and preview guidance.
- `594338d`: tested IP-health foundation and ASUS integration checkpoint; user-facing route remains hidden.
- `3351dd3`: verified ASUS package rollback, legacy DNS worker quiescence, pending-package classification and unified current-package bootstrap path.

## Completed reliability changes

Healthy foreign Entware policy flags no longer count as unfinished installations. Real ARM Entware opkg produced the failing hold/noprune examples before the fix. Own-package hold policy and true unfinished states remain guarded. Historical operation errors are qualified separately from fresh check failures. Background busy polls retain validated state. A known applying operation has a bounded 120-second transport grace; auth/manual errors remain visible.

For a healthy installed baseline, the worker captures local package payload, own manager metadata, settings and guarded auxiliary state under the real opkg mutex before stopping core/web. On caught install/postflight failure it uses real opkg with the sealed local rollback IPK, restores exact settings/metadata, verifies the old package and then restores running/stopped/WAN-wait intent. New signed stock seeds are quarantined only on exact absent-baseline path/hash/mode matches. Unknown custom changes, foreign package changes, unsafe links, failed process quiescence or failed verification never produce a restored-success claim. Snapshots and logs remain private.

Old queued SmartDNS CLI workers are quiesced by exact process identity. Fresh resume loads action classes after acquiring the update lease. ARM32 monotonic deadlines use float seconds. Transaction postinst does not start web/core or queue stale DNS code. Both installer closures were regenerated with validated launcher hashes. Current packages with the report baseline use the same staged coordinator from the one-command entry; older bootstrap compatibility and fresh dependency installation remain separately tested.

Timer sign-in recovery preserves interval/watchdog drafts and never automatically repeats Save. Read-only recovery and local sign-in remain dismissible during stalled requests. Preview hover/mobile tap names missing fields; JSON download works without a configured sending channel. Catalog failure messages distinguish DNS/TLS/runtime/HTTP/connectivity without weakening signatures or certificates. Docker/Compose MTProto overrides the pinned image entrypoint consistently and requires a nonce-checked Telegram response; native remains Python, not the reported unrelated Rust ARM binary.

## Verification at this checkpoint

- Updater backend: 227 tests passed, five missing frozen relay fixtures skipped.
- Installer: 59 passed, including actual Entware opkg configure80 → upgrade81 with coherent metadata.
- Native POSIX launcher tests: 10 each on host, ARMv7 and AArch64; both cross-built binaries/inventory reproducible.
- ARMv7 staged PHP runtime: six passed. Quiescer also tested against actual PHP8.2/8.4 ARM32 with working and ignored TERM.
- Timer browser: 40 RU/EN cases passed. Updater recovery browser: 32 passed.
- Catalog: 43 of45 Python cases passed, two optional CGI skips; signed live catalog control and browser/session races passed.
- IP-health: 54 backend/runtime/ASUS/Lua/platform cases plus both browser suites passed; this is not live NFQUEUE proof.
- Share/MTProto client, browser and install regressions passed. Five builder boundary tests passed.
- Final frontend TypeScript and Vite build passed; existing bundle-size warning remains.
- Regenerated root/source installer bytes and trusted embedded closures match. No unresolved tracked diff whitespace errors.

## Required continuation before release

1. Package IP-health Lua/worker/ASUS adapter and resolve the sockets dependency transition. Adding `php8-mod-sockets` directly to Depends currently conflicts with strict updater dependency equality. Do not globally relax dependency checks or let opkg upgrade unrelated installed dependencies. Missing sockets must remain fail-open without creating a ban journal.
2. Implement and verify native OpenWrt nft/procd wiring before exposing IP-health there. Current native HTTP endpoint refuses it after auth/CSRF; native packaging has not been changed.
3. Prove actual router queue ownership, marked probes, DNS filtering, client exclusions, IPv6-off, dual-WAN behavior and TTL failure-open; verify timer, update and rollback interactions on hardware. Tests so far use real PHP/Lua processes with isolated packet/runtime fixtures.
4. Expose the tab/route only after packaging and real integration checks. Persistent bans/history are under `/opt/etc/nfqws2/ip-health/bans.json`, inside the existing recursive settings snapshot. RAM observer files do not loosen the main core's private runtime directory.
5. Power loss/SIGKILL during the opkg critical boundary remains an interrupted-operation diagnosis, not automatic reboot-time rollback. A pending baseline uses signed guarded configure recovery, not a promise of an earlier healthy payload. Preserve these distinctions in release claims.
6. Produce and inspect complete packages for all intended architectures, perform the final whole-branch review and publish only after the above delivery requirements are satisfied.

The user's own 79→81 update succeeded. Other users' video shows installed81 plus a pending-packages warning, but does not reveal the actual DB rows or whether the error is historical. The original interruption cause on each affected router is still unverified; do not assign all reports to one cause.

## Authorized hardware continuation, 1 November

Both owner's routers may be used, including temporary service starts. Their initial stopped/disabled intent must be restored after testing. Do not access or involve the earlier third-party router.

- Main Merlin AArch64: actual published81 coordinator installed the private82 candidate successfully, retained settings and restored the running test intent. The private test changes only delivery transport; signatures, sealed coordinator, native manager mutex and postflight remain active. This is not a public HTTPS/UI delivery test.
- Marked socket probes succeeded on actual Merlin PHP8.4 and native OpenWrt PHP8.3 using matching official modules staged privately. Modules were not installed by those probes.
- Stock Merlin root-owned writable system mount parents exposed an IP Health path-guard incompatibility. Fixed platform anchors now accept the stock boundaries while rejecting writable managed descendants, neighboring mounts and unsafe files/links. Nine permission regressions and184 related tests passed without changing system directory modes.
- A deliberate private postinst failure reached real package downgrade, but the original automatic finalization failed. Its exact live failure remains unresolved. The owner device was manually restored from its sealed snapshot through real opkg and guarded local finalization; settings and foreign package metadata were verified. This manual rescue is not evidence that automatic rollback passes.
- Entware can leave its root-owned `.list` inventories at0666. A dedicated bounded/stable index reader now handles that legacy mode only for manager inventories, validates closed project paths and excludes foreign package claims. Payload/root/link guards remain strict. Six exact80/81/82 package layouts and real-manager regressions passed. Independent review reproduced and closed a repeated-slash alias bypass.
- Private closed stage diagnostics now distinguish entry/runtime/context/authorization/environment/restore/receipt failures, without public paths, process IDs or raw exceptions. Expired-operation cleanup includes their exact filename. Broad updater257 tests passed with five unavailable frozen-relay fixture skips; final70 targeted tests passed.
- Final installer closures were regenerated and independently compared to all126 PHP modules and launchers. Installer SHA256: `c241ecad9c83967756277eb7d2ee4f40b6b1a802e5445b1d53d90b9ac768f3c5`. Full installer59 passed before the final single parser predicate; the two closure extraction/tamper/parity checks passed again afterwards.

Still required: install the freshly rebuilt diagnostic candidate, reproduce and fix the live automatic-finalization failure, verify actual IP Health queue/DNS/client-exclusion/fail-open behavior, exercise timer/watchdog on hardware, restore initial service intent, build and inspect the intended release matrix, then perform final review before publication. Native IP Health API remains intentionally gated until its complete delivery path is verified.

### Subsequent hardware findings

The automatic-finalization failure is now reproduced and fixed: Entware's committed database can temporarily contain only historical removed own-version records during downgrade postinst. These records must be validated and skipped, rather than substituted for a live installed row. Healthy snapshot/postflight still require an active installed package, and unexpected live versions remain rejected.

A subsequent real hardware failure trial passed automatic rollback: fixed postinst failure, real manager downgrade, restored healthy82, verified settings, preserved foreign database records and fresh running core. The deliberately failing target changed PHP payload bytes; their baseline hashes were restored as well. Private delivery injection still excludes public HTTPS/UI transport from this proof.

Native OpenWrt24 hardware exposed a separate optional-`stat` dependency in package-default guards. Equivalent base numeric-`ls` and inode-identity checks removed it. Real native installation then completed with core disabled/stopped and web running as before. Isolated24/25/nft fixtures passed45 tests without skips, including actual interrupted-configure and crash/default ownership cases.

IP Health delivery still requires final hardware proof. Its shared bounded manager-data reader now handles both legacy0666 inventories and the fixed status file without chmod or database writes. Hardware also proved that daemon NFQUEUE port IDs differ from daemon process IDs; queue ownership must be established through the netlink socket inode held by the registered process, rather than numeric PID equality. That runtime correction and subsequent packet tests remain in progress.


### Final frozen payload verification, 2 November

The final source freeze includes the closed Conffiles factory baseline and declared-ownership union. Rollback archives carry the two pinned factory seeds; the owner's separate private snapshot restores their actual settings. A failed rollback postinst may leave those retained Conffiles out of the real manager's inventory. Exact configure and the next snapshot accept only the two validated declarations, never an unknown or foreign-owned path, without rewriting the package database or inventory. Real Entware tests cover subsequent ordinary upgrade and interrupted-configure recovery with custom owner settings.

The final frozen AArch64 package passed a deliberate postinst failure on the owner's Merlin: automatic return to healthy82, byte/mode-exact preservation of all91 settings files, unchanged foreign package records, and the original stopped service intent. Panel service returned. The trial included custom authentication and sending-channel settings; factory baseline hashes remained correct after rollback. A subsequent ordinary signed preparation succeeded; its private test candidate was closed and normal public discovery restored. A fresh real rollback capture/load/installed verification after that rollback also passed, with both retained Conffiles absent from the actual manager list. All310 payload files were captured; manager status, list and operation journal remained byte-exact. Earlier test-only tainted metadata was repaired separately through authenticated real-manager version changes; that private lab procedure is not part of the shipped updater.

IP Health hardware verification passed queue ownership through the daemon's netlink socket inode, marked probes with the exact matching official PHP sockets module, actual mixed UDP DNS answer filtering, fast TCP/UDP443 refusal, client exclusion, IPv6-off and expired-worker fail-open behavior. Packet tests injected an explicit test address; they are not evidence that a particular real provider block was diagnosed. Simultaneous multiple WAN and encrypted/TCP DNS remain outside the feature's supported path. Native OpenWrt IP Health remains API-gated.

Timer hardware verification passed one scheduled restart, no immediate repeat, one delayed watchdog recovery after a controlled process exit, and no restart after manual stop. Original timer and IP Health settings absence was restored. BusyBox background worker lease inheritance was reproduced and fixed; apply/core leases remain independently acquirable while the worker is alive.

The final native Cortex-A9 package installed successfully on the owner's second ASUS with core disabled/stopped and the panel running. Both routers retain their original stopped/disabled core intent and original owner settings. Only the normal learned auto.list content grew during the running-core tests; it is retained.

Final updater suite:270 cases,265 passed and five skipped because the frozen64/65 relay archives are unavailable. Exact80/81 compatibility cases, ARM32 PHP8.2/16MB Conffiles cases, real Entware manager recovery cases, actual AArch64 PHP/OpenSSL cases, sockets/lease cases and frontend session/timer checks passed. Both ASUS packages reproduce byte for byte; all20 native artifacts match source and APK signatures. Source and release assembly exclude generated caches, private hardware helpers, credentials and operational profiles.

Release publication remains pending final source archive and delivery verification. Power loss or SIGKILL in the native manager critical boundary still requires interrupted-state diagnosis; this is not a tested reboot-time automatic rollback promise.
