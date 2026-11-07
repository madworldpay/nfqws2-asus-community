# Device profiles beta

This directory contains the shared beta editor, strict planner, isolated strategy library, activation journal and platform adapters included by the ASUS/Entware and OpenWrt package builders. The default remains Common; saving or previewing a draft never applies traffic. See [the user guide](../../docs/DEVICE-PROFILES.md).

Distinct selected strategies run as separate engines, with at most four additional NFQUEUE queues41000–41003. Ordered goto dispatch makes the first matching card own the selected device's traffic; the normal service configuration stays the fallback. Native procd/nftables and ASUS daemon/iptables adapters use the ordinary service/update leases and verify process/socket ownership. Imports use the existing bounded document validator and isolated resource copies; DNS is shared.

The journal records original state before mutation, phases, the original failure and verified recovery. A detached worker and guard outlive the page. Before upgrading while split routing is active, users apply Common. Package integration is generated from exact known hook layouts and carries a manifest; unknown layouts abort the build.

The earlier compile_probe.py is a historical single-engine mark feasibility probe. It is not the shipped multi-process runtime. Tests cover validators, file boundaries, priorities, imports, failure recovery, native/Entware rendering, packaging and the browser. Hardware checks and deployment evidence are maintained privately rather than embedded in public source.
