# Native OpenWrt packages

## Intent and authorization
The owner requests the existing NFQWS2 application on OpenWrt, initially on ASUS families and then on other OpenWrt devices. They selected native OpenWrt packages and explicitly delegated technical decisions in this chat. This is a new platform implementation with the same application, not an Entware prerequisite or a per-brand fork.

## Goals
- Reuse the current RU/EN frontend, author-defined JSON import selection, cloud catalog, strategy editor, client selection, diagnostics/export, SmartDNS, and update experience.
- Produce native IPK for the 24.10 line and native APK for the 25.12 line. Native package architecture comes from OpenWrt package metadata, not uname alone or the marketing model name.
- Package only the selected architecture engine. Use OpenWrt dependencies for PHP, the web server, libraries, and kernel modules. Do not bundle foreign Entware libc or ASUS kernel modules.
- Discover logical WAN devices through ubus/netifd, including PPPoE, VLAN, multiple active uplinks, IPv4 and IPv6. Do not assume eth0, a fixed LAN bridge, or ASUS port numbering.
- Use procd for service supervision and firewall4/nftables for modern OpenWrt. Rules are owned by this application, reloadable, idempotent, and removable without flushing third-party firewall state. Select clients in both conntrack directions.
- Account for software/hardware offloading and third-party acceleration. Report actual queue delivery; a running process with no observed packets is not proof of working traffic interception.
- Preserve existing DNS, VPN, routing, and operator edits. SmartDNS manages a separate service/configuration and a bounded DNS integration with confirmation and rollback.
- Keep install/update disabled on first install; preserve previous service state on upgrade. Validate platform, package format, architecture, payload, free space, and package-manager errors before claiming success.
- Retain current ASUSWRT/Entware behavior and release channel. A native client must never install an Entware package, or vice versa.
- Reuse the same cloud catalog; JSON path and built-in blob references must remain portable across native/Entware layouts. No private presets or credentials enter source/release files.

## Scope boundaries
The package uses a working OpenWrt installation; it does not add firmware hardware support. Begin with the actual arm_cortex-a9 RT-AC87U. Other families receive build/runtime checks appropriate to available tools; only actual hardware tests are labeled hardware verified. Limited storage has an actionable requirement rather than an unsupported-brand error. No automatic firmware upgrades or changes on the main ASUS/Keenetic.

## Approaches
1. Native OpenWrt: chosen by owner. Common UI and data contracts, explicit platform adapters, native dependencies and package formats. More initial integration work, best long-term portability.
2. Entware compatibility: considered and rejected as the main approach. Faster initial reuse but adds a second environment and retains foreign ABI/system assumptions.

## Structure
Keep common UI/data logic under source/project/webui. Keep the current ASUS adapter and builder. Add source/project/openwrt for native detection, service/firewall/DNS adapters, packaging, and tests. Explicit platform/profile resolution selects trusted built-in paths and commands; no arbitrary browser-supplied executable paths. Do not create global /opt aliases or pretend ASUS nvram/cru commands exist.

## Architecture/family matrix
Audit input is official OpenWrt 25.12.6 profiles.json files. ASUS currently spans 53 profiles, 12 targets, and 7 package architectures: arm_cortex-a9, arm_cortex-a7_neon-vfpv4, arm_cortex-a15_neon-vfpv4, aarch64_cortex-a53, mipsel_24kc, mipsel_74kc, mips_24kc. Support general OpenWrt ARM/ARM64/MIPS/MIPSel and x86 variants when a verified engine exists. The mapping is by architecture/ELF compatibility, not a device whitelist. Distinguish endian, ELF class/machine, ARM CPU baseline, and soft/hard-float requirements.

## Platform boundaries
- Paths: native /etc/nfqws2, /usr/lib/nfqws2, /usr/share/nfqws2, /etc/nfqws2-web and /tmp runtime; persistent config vs bounded RAM jobs are explicit. Existing Entware paths remain unchanged.
- Lifecycle: procd start/stop/reload/respawn, actual process identity and queue health, network/firewall reload and reboot persistence.
- Firewall: own inet table/rules, selected uplinks and clients, processed-mark bypass, NFQUEUE bypass, no diversion of unrelated VPN traffic. Native dependencies install the matching queue modules from the firmware feed.
- DNS: own SmartDNS instance, managed dnsmasq integration for supported resolver owners, descriptive conflicts for another resolver owner, transactional restoration only of owned state.
- Web: shared panel on a dedicated LAN-scoped listener, authentication retained, no changes to LuCI's listener/firewall exposure. Native PHP/runtime and controlled commands.
- Import/share: portable paths and blob recognition; round-trip author choices, preview/undo, preserve working config, safe bounded diagnostics.
- Updates: distinct native identity/channel; validate OS/release/format/architecture before package-manager execution; retain user config and enabled state; no signature weakening.

## Verification and acceptance
Tests must fail before each new behavior is implemented, then pass. Compile/lint the shared frontend and run relevant existing ASUS suites. Exercise native package contents and ELF metadata for supported families, opkg/apk separation, and rejecting a mismatched package before service/network changes. On the 87U: installation, login, core start/stop, actual forwarded queue traffic, client selection, cloud/file imports and undo, DNS apply/confirm/rollback, DPI collection/export, reboot/reload, update and removal. Preserve an external backup before router changes. Publish only after the claimed features have passed; distinguish build-tested and hardware-tested families.
