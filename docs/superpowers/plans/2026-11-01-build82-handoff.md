# Build 82 preparation checkpoint

Branch: `fix/build82-reliability`. Public main remains unchanged. No Build82 release, replacement Build81 assets, router update or live firewall changes were made in this preparation.

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
