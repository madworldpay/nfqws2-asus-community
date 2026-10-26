# Native OpenWrt Implementation Plan

> For agentic workers: use superpowers:executing-plans to implement this plan task by task. The owner delegated technical decisions and inline implementation is selected.

**Goal:** Deliver native OpenWrt packages of the existing NFQWS2 panel and services across CPU families without a brand whitelist.

**Architecture:** One frontend and data contract, separate ASUSWRT/Entware and native OpenWrt platform adapters. Native dependencies and package formats; no global /opt emulation. Validate the actual operating system and capabilities at runtime.

**Tech Stack:** POSIX shell, Python build tooling/tests, existing PHP backend and React/TypeScript frontend, procd, ubus/netifd, firewall4/nftables, OpenWrt package tools/SDK.

**Spec:** docs/superpowers/specs/2026-10-25-native-openwrt-design.md

## Global Constraints
- Preserve existing ASUSWRT/Entware behavior and release channel.
- Native IPK for OpenWrt 24.10; native APK for OpenWrt 25.12.
- Native /etc/nfqws2 configuration, OpenWrt dependency packages, matching kernel modules; no Entware libc or global /opt alias.
- First installation leaves traffic processing off; upgrades preserve config and enabled state.
- No changes on the main ASUS or Keenetic; real tests use the spare RT-AC87U.
- No private presets, credentials, or detailed strategy parameters in source/public release notes.
- No claim of hardware verification for emulated/build-only platforms.

## Review Focus
- WAN names change after PPPoE reconnect, IPv6 differs, multiple WAN/VPN interfaces exist: discover current logical uplinks and retain unrelated routing.
- An acceleration engine bypasses hooks: process liveness does not become a false success; ownership and restoration of any settings changes are checked.
- Imported JSON uses Entware/native absolute paths, built-in blobs, or author-disabled blocks: normalize only known resource paths and preserve selection semantics.
- Installation/update fails or reboots between steps: retain user config, restore prior service state where safe, expose an actionable failure.
- Another DNS service or administrator modifies state while SmartDNS is active: restore only owned values and never overwrite unrelated edits.

### Task 1: Platform and architecture contracts
Files: openwrt/platform.py, openwrt/architectures.json, tests/test_openwrt_platform.py; platform/path contract used by later tasks.
Interfaces: resolve_platform(release, board, package_manager, architectures) returns OS, release series, package format, target, package architecture and engine family. validate_engine(data, target) checks ELF class/machine/endianness; no model whitelist.
- [x] Write behavioral tests for RT-AC87U, Qualcomm ARMv7, MediaTek ARM64/MIPSel, big-endian MIPS, x86_64, apk vs opkg, corrupt metadata and mismatched ELF.
- [x] Run and confirm missing implementation failures; implement strict deterministic resolution.
- [x] Run platform tests plus existing builder/platform regression baseline; commit.

### Task 2: Native service and nftables delivery
Files: openwrt/platform.sh, openwrt/firewall.sh, openwrt/nfqws2.init, openwrt/defaults.conf, tests/test_openwrt_firewall.py, tests/test_openwrt_lifecycle.py.
Interfaces: nfqws2-native {start,stop,reload,status,check,diagnostics}; diagnostics reports process and queue facts, selected uplinks and acceleration state.
- [x] Write failing tests for logical WAN discovery, multiple WANs, both conntrack directions, selected clients, queue bypass, repeated reload and removal of only owned state.
- [x] Implement procd supervision and a rendered own nftables ruleset; bounded literal config parsing and argument handling reuse existing validated strategy semantics.
- [x] Test failure rollback and offload ownership/restore; compile nft rules in a native test environment.
- [x] Commit after the suite passes.

### Task 3: Native packages and real core installation
Files: openwrt/build.py, openwrt/assets.json, tests/test_openwrt_builder.py.
Interfaces: build_native(release_series, package_arch, engine_asset, output) emits a package and checksums; installs native paths with explicit dependencies and conffiles.
- [x] Test package file ownership, correct package architecture/format, no foreign loaders/modules, preserved config and disabled first install.
- [x] Implement official native package-tool pipeline with pinned engine/source digests; use selected architecture payload only.
- [x] Build/install the IPK on 87U with processing off, then verify check/start/traffic/stop and restore test state.
- [x] Build-check APK and remaining engine families; commit.

### Task 4: Shared panel native platform adapter
Files: common PHP platform/path/service boundaries, native web service adapter, tests/test_openwrt_web.php, existing backend/frontend regression suites.
Interfaces: trusted build/runtime profile resolves paths, service commands, model/system facts, WAN facts and capabilities; ASUS profile remains default for the existing builder.
- [x] Write failing path/service/auth/API tests for both profiles, including symlink and unknown profile rejection.
- [x] Replace firmware assumptions through explicit boundaries rather than source-wide blind path substitution.
- [x] Use a native dedicated web listener without changing LuCI. Adapt checkup/WAN facts and show hardware-specific controls only when present.
- [x] Build/lint frontend, run backend regressions, verify actual native login/config/start/status in browser; commit.

### Task 5: Portable import, cloud catalog, diagnostics and export
Files: common import/resource path abstraction, native DPI/diagnostics runtime adapter, tests/test_openwrt_import.php, tests/test_openwrt_diagnostics.php.
- [x] Test native/Entware JSON round trips, author defaults, built-in/custom blobs, preview/apply/undo and hostile/traversal paths.
- [x] Adapt only trusted known resource paths, retain schema/author intent and the existing cloud catalog endpoint.
- [x] Integrate native DPI binaries/jobs and safe support/export facts; test terminal states and cancellation.
- [x] Exercise local JSON and cloud profile through the real panel plus DPI collection/export; commit.

### Task 6: Native SmartDNS with owned resolver integration
Files: openwrt/smartdns adapter and common lifecycle/platform boundary; tests/test_openwrt_smartdns.py/php.
- [x] Test dnsmasq integration without replacing existing server/ipset/nftset entries, multiple instances, another resolver owner, reboot, rollback and concurrent operator changes.
- [x] Implement a separate native SmartDNS process and managed resolver state, preserving current apply/confirm/undo semantics.
- [x] Validate actual LAN DNS with core on/off and a disposable VPN/DNS fixture; commit.

### Task 7: Native updates and install selection
Files: native release/format resolver, native update lifecycle, installer platform branch, tests/test_openwrt_updates.py/php.
- [ ] Test native/Entware cross-install rejection, wrong architecture/format, corrupted downloads, low storage, partial package-manager failure, enabled-state restoration and old frontend compatibility.
- [ ] Implement distinct signed native release identity and manager dispatch; reuse common release-history presentation.
- [ ] Verify native upgrade, failed upgrade and removal on 87U; preserve main ASUS behavior; commit.

### Task 8: Cross-family verification, documentation and review
Files: OPENWRT.md, English equivalent, build/runtime matrix, source packaging and CI rules as appropriate.
- [ ] Run relevant common ASUS regression suites and native suites; build/lint frontend.
- [ ] Verify 87U start/stop, NFQUEUE packet delivery, client scope, DNS, import/export, update and reboot; retain results privately.
- [ ] Build/ELF/runtime check available non-ARM families; mark limits explicitly.
- [ ] Fresh whole-branch review, fix important findings with failing tests first, then prepare reviewable artifacts/docs and publish only verified outcomes.
