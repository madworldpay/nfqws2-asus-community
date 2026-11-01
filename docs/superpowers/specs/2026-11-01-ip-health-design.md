# Confirmed unavailable IPs

The user approved the preliminary dark panel and requested implementation without repeated setup questions. Preserve NFQWS2 and saved strategies. Address IP-wide silent TLS failures independently of ordinary strategy selection. This is a reachability heuristic, not proof of provider intent or a universal iOS Shorts fix.

## Architecture and choices

Use a second, observation-only instance of the pinned NFQWS2 1.0.6 engine on a distinct queue. Its Lua profiles observe TCP443, refuse already confirmed TCP443/UDP443 destinations and conservatively filter UDP DNS answers. The original daemon and its strategy arguments stay unchanged. This avoids hostlist/SYN blindness and profile-shadowing in a leading ban profile. Root-owned runtime manifests expire if the controller stops. The additional queue is bypassable and has bounded flow/event storage.

A root PHP controller consumes bounded untrusted observations, performs independent numeric-IP TLS probes with SO_MARK=0x40000000, and persists confirmed incidents. On ASUS, a matching pinned official php8-mod-sockets package is acquired separately when needed; the main package dependency contract stays unchanged. Native OpenWrt keeps the IP-health API and tab gated until its complete capability delivery path is verified. Probe EOF/reset/alert/data never establishes a ban. Only repeated independent silent ClientHello observations followed by two silent neutral-SNI probes, with a recently responsive control probe on the same single uplink, can establish an incident. Missing socket/mark support, invalid time, multi-WAN, controller failure or absent core must fail open and report unavailable/stopped.

Compared alternatives: a new first NFQWS strategy can shadow user profiles and an empty IPset can match all traffic; kernel timeout sets require additional firmware-specific modules. The separate observer costs a second small engine process and queue, but isolates its failures and leaves user strategies intact.

## State and interfaces

Shared PHP classes live in webui/web/public/ip-health-{store,probe,controller,api}.php. Persistent ASUS state is /opt/etc/nfqws2/ip-health/bans.json; native state /etc/nfqws2/ip-health/bans.json. ASUS public RAM manifest/events live under root-owned 0755 /tmp/nfqws2-asus-ip-health; private process facts remain under 0700 /tmp/nfqws2-asus/ip-health-private. Native RAM integration is pending. No per-packet flash writes. Store operations are locked, bounded, atomic and reject symlinks/unsafe ownership. First distinct incident lasts 86400 seconds, recurrence within retained 30-day history lasts 604800 seconds. Repeated packets during an active incident do not escalate it. Keep at most 512 entries/history items. Retest every 900 seconds; three responsive checks lift a ban. Network generation changes suspend old evidence until independently revalidated. Disabled mode preserves history and immediately stops enforcement.

HTTP commands: iphealthstatus; iphealthconfigure(enabled='1'|'0', revision); iphealthremove(id,revision); iphealthclear(revision); iphealthrecheck(id='all'|entry id,revision). All require the panel's existing authentication, same-origin and CSRF checks; mutations also take the updater lease. State revision is SHA256 over user-visible effective ban membership/settings; no arbitrary endpoint, command or path is accepted.

Status JSON: schema_version=1; revision=64 lowercase hex; enabled=boolean; runtime={state:'active'|'starting'|'stopped'|'unavailable',code:string|null,updated_at:int|null,dns:'router_udp'|'unavailable'}; entries=[{id:32 lowercase hex,ip:string,port:443,host:string,until:int,first_seen:int,incident:1|2,last_check:int|null,check_state:'due'|'checking'|'silent'|'replied'|'unknown'}]. Actions return the same status. A failed reply is not retried automatically.

Root manifest RAM file active.txt, atomically replaced mode0644 in root-owned directory: first line IPHEALTH1; second line `expires <epoch>`; third line `enabled 0|1`; subsequent `ban <canonical IP> <until>`. Limit512 bans. Expiry is at most15 seconds ahead; wall clock must be sane. Lua reads at most65536 bytes no eval. Worker config runtime.json is root-only and supplies platform paths, generation, interface and core PID; shell creates it from fixed validated facts.

Observer event append file events/events.log, engine-user-owned RAM directory, capped262144 bytes. Lines `silent|<epoch>|<ip>|<clientport>|<hostname>` or `reply|<epoch>|<ip>|0|`. Candidate timestamps and flow tuple deduplicate independent observations; worker validates all fields, public IP and hostname. Raw input never becomes shell code. Root opens only a verified regular single-link file and checks opened inode before truncation/consumption. Lua pending flows max512, silence3000ms, lifetime15000ms.

## Packet and DNS behavior

Only selected clients and the selected uplink are observed/enforced; excluded IoT and IPv6-off settings apply equally. TCP reset and UDP ICMP refusal must identify the client tuple and carry the existing desync mark. Current TCP flows can be reset after confirmation without waiting for another retransmission. No global UDP443 blocking and no ban from a QUIC-only failure.

Capture plaintext UDP DNS replies from the router to selected LAN clients and external resolvers on the selected uplink. Rewrite only a bounded successful untruncated single-question response with A/AAAA/CNAME answers, no authority, and at most an ordinary OPT record. Skip DNSSEC DO/signed/unsupported messages. Decode compression and rebuild names safely. Remove banned address records only when an unbanned usable address of that requested family remains; otherwise preserve the original answer. DoH/DoT applications and TCP DNS remain unchanged and the panel states the limitation. No forcing private DNS off.

## UI and verification

Use the approved preview layout as a real RU/EN panel tab, mobile cards, clear confirmation, per-entry recheck/remove and a non-destructive toggle. Show service readiness and honest errors, never empty-success on API failure. DNS scope is explicit. No demonstration entries in production.

Test store expiry/recurrence/network change/clock/concurrency/bounds, probe silence vs reset/EOF/reply/control failure, real Lua parsing/packet reconstruction/DNS compression, firewall/client/mark/queue ownership and cleanup, API auth/CSRF/lease, real browser actions RU/EN/mobile. Package both platforms and verify their exact new runtime payloads. Build80 public release remains immutable; release publication is a separate step after integration evidence.
