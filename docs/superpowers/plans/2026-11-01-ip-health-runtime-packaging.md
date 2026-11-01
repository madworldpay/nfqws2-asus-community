# IP Health runtime packaging and native validation

Worktree checkpoint from 35e3094, Build82 preparation only. No live router access, release, commit or publication was performed by this worker. Native API remains closed until the complete feature is verified. UI exposure belongs to the parent task.

## Deployment contract

ASUS preserves the released Depends list byte-for-byte. The builder installs `runtime.sh`, `worker.php`, `dns.lua`, `monitor.lua` from `source/project/ip-health/` under `/opt/lib/nfqws2-asus/ip-health/`, all 0644; `control.sh` is additionally installed 0755 for fixed asynchronous reconcile. The shared public PHP backend is copied only when its bytes exactly match source; stale dist is rejected.

Optional ASUS sockets data is under `/opt/share/nfqws2-asus/ip-health-sockets/catalog.json` and `ipks/<official filename>`, all 0644 and root-owned. ARM packages contain both armv7-2.6/PHP8.2.8-1 and armv7-3.2/PHP8.4.16-4; AArch64 contains only its 8.4.16-4 variant. The catalog pins the complete archive and the only two regular payloads: `opt/etc/php8/20_sockets.ini` and `opt/lib/php8/sockets.so`. Official archives have no maintainer hooks or conffiles. PHP-3.01 license is included. The fixed capability worker/control and dedicated sockets launcher are also packaged; their policy and explicit enable integration are owned by the separate sockets worker task; these archives are inert package data and are never globally unpacked by the own package.

Native installs `/usr/lib/nfqws2/ip-health/{runtime.sh,worker.php,dns.lua,monitor.lua}` 0644 and `service.sh` 0755. Its existing core procd service adds an optional `iphealth` instance without respawn or separate boot enable state. The worker uses canonical private `/var/run/nfqws2-native/ip-health-private`, public `/tmp/nfqws2-native-ip-health`, shared PHP under `/usr/share/nfqws2-web`, engine `/usr/bin/nfqws2`, and journal `/etc/nfqws2/ip-health/bans.json`. Startup holds a short ordinary update lease; the foreground supervisor explicitly closes it before the long worker loop. Worker exit tears down its observer/table.

DNS replies to the router itself never enter the health queue: forwarded client DNS uses FORWARD and local resolver replies use OUTPUT. This prevents filtering a shared upstream cache from leaking across excluded clients. TCP monitoring still uses PREROUTING.

Native rules use an atomic create-only `inet nfqws2_health` table with exact owner comment. Queue is main+1, with bypass and marked-probe return. Hook priority -149 follows the existing main capture; client scope, local DNS destination scope, IPv6-off, foreign queue and multiple actual uplinks are checked. Core stop removes only the sidecar's own table and process identities. No main arguments or independent boot intent are added.

Native Depends also remains unchanged: native update dry-run currently refuses extra package changes. Optional native sockets acquisition must be resolved separately against exact firmware/PHP/feed ABI; the ASUS Entware IPKs must never be installed there. Without sockets/SO_MARK, native sidecar returns unavailable and leaves the core running.

## Isolated verification and important findings

- Emitted ASUS ARM/AArch IPK tests inspect exact own runtime/backend bytes, root ownership, modes and unchanged dependency metadata. External downloaded ELF archives are fixtures in this unit suite; full real cached builds remain separate evidence.
- Native shell/procd tests cover queue/client/IPv6/mark scope, stopped core, foreign queue/table, multi-WAN, missing sockets, short startup lease and loop-exit cleanup.
- Real nft1.1.6 in bridge-only `nfqws-openwrt25-net-test` accepts/creates/removes the generated table. Queue 301 carries bypass; hook priority is -149; fw4 before/after JSON is byte-identical; a foreign reserved table survives apply and stop attempts. This is real kernel transaction proof, not hardware packet/DNS proof.
- Unskipping the existing native engine tests found an older packaging regression: shared SmartDNS control now has two delayed backend includes, but the native builder assumed one common prefix. Its early intent precheck also still used the ASUS path. Exact individual replacements now preserve native intent and deferred loading. An executed emitted-control regression proves native resume reaches its lifecycle only after its update lease.
- The existing offline-install fixture created group-writable `etc` under the developer umask. Correcting the fixture to firmware-safe 0755 makes its existing strict parent gate meaningful; production permission checks remain unchanged.

## Final targeted verification

135 tests passed with explicit PHP sockets, pinned real engines, real OpenWrt JSONfilter and the isolated native nft container; no skips in that run. Suites: IP Health backend/runtime/ASUS/control/Lua, ASUS builder/packaging, native sidecar/builder/firewall/lifecycle/package lifecycle/update service lease/native runtime.

ASUS asynchronous reconcile uses a separate root-private duplicate lease, drops inherited apply leases, and survives process-group HUP. Read-only enabled admission honors saved disable. Module acquisition is queued only if the PHP module is absent/unloadable: unsupported SO_MARK/BINDTODEVICE with an already loaded module remains unavailable without an acquisition/reconcile loop.

## Reproducible local inputs

- Existing verified ASUS cache: `<private-repair-cache>/release67-20261022/cache` (all original 11 ASSETS match).
- Three independently verified official sockets IPKs and QEMU loader evidence: `<private-repair-cache>/build82-php-sockets-20261101`.
- Native tools, pinned source, SmartDNS archives and uncompressed engines: `<private-repair-cache>/openwrt-universal-20261025/runtime`.
- Host UPX: `<private-repair-cache>/release69-20261024/upx`.

## Owner hardware handoff (parent executes)

Owned spare RT-AC87U reports OpenWrt 24.10.8/kernel6.6/ARMv7, package 72 stopped and disabled, web running, PHP 8.3.36. Preserve this exact baseline. Inspect candidate payload/package identity before installing; do not let package hooks enable or start main.

1. Record service `enabled`, `running`, procd registration, `/proc/net/netfilter/nfnetlink_queue` and `nft -j list table inet fw4`; record absent/present journal and own sidecar table without exposing content.
2. With main still stopped, run `/usr/lib/nfqws2/ip-health/service.sh` under a 15-second outer bound. It must exit without observer queue, health table or ban journal; main remains disabled/stopped.
3. Missing-sockets case: use an outer cleanup trap and a bounded transient `/etc/init.d/nfqws2-native start` (never enable). Verify the main queue/health remain correct; no health queue/table or journal is created. Capture unavailable/socket status from public RAM. Stop main and restore disabled state; compare fw4 and queues to baseline.
4. Only after the exact native PHP 8.3.36 module is independently verified, repeat the bounded transient start. Inspect procd main+iphealth, main queue+derived queue, protected worker/observer identities, own nft table, expiring root manifest and unchanged custom/client settings. Stop must remove both queues and health table and preserve disabled state. Do not substitute an Entware module or upgrade PHP.
5. Actual marked probes, DNS answer filtering, fail-open TTL during controller loss, IPv6-off/exclusions/network changes and timer/update/rollback interactions still require targeted hardware packet tests. Unit/Lua/container results do not substitute for them. Keep native API and UI unavailable until that evidence exists.

Real-cache proof artifacts (not final UI/release packages): `<private-repair-cache>/build82-ip-health-packaging-20261101/proof-final-owned`. Both ASUS architecture IPKs and native 24.10 ARM IPK built offline and passed emitted byte/mode/owner/DNS-hook/dependency checks. Static frontend is the earlier built dist plus exact current public PHP snapshot. Native application_build remains source 81 until final build identity freeze; do not publish these proof artifacts. No APK/all-architecture release matrix or live packet claim is made here.

Review fix: ASUS forwarded DNS now enters an owned `nfqh_forward` chain whose only jump to `nfqh_local` matches the generation WAN ingress. Renderer regressions prove eth0 transit queues while tun11/wg0/br1 transit does not, across all/include/exclude modes; OUTPUT remains unchanged. Cleanup uses recorded own chain names independently of the current interface and removes the prior unpublished broad hook when owned. Native already requires matching WAN ingress plus reply direction; its renderer and real nft suite were reverified. The earlier private proof IPKs predate this review fix and must not be used as the final hardware candidate; parent rebuilds from the frozen source. Shell/ash syntax and the complete 135-test targeted suite pass.
