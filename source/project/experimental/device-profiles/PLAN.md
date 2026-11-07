# Device profiles experiment — 7 November 2026

Owner-authorized standalone prototype for RT-AC87U, using the existing panel authentication. This directory is excluded from release integration: no public build or automatic migration is requested. Working traffic is never changed through this prototype.

The experiment presents Common mode by default, discovers known LAN devices, permits manual named IP/MAC entries, and exposes ordered per-device profiles only in Split mode. Profile cards are reordered by drag handle or up/down actions. An explicit draft save persists the order and manual device identities; a separate preview explains enabled matching profiles and the existing current-strategy fallback. The first applicable strategy is a proposed runtime rule; no traffic-application claim is made.

Tasks:

- [x] Back up the 87U config/resources/index and firewall state.
- [x] Implement strict bounded PHP draft validation, atomic revision-checked storage, LAN-only discovery, and priority preview. Test validation, stale writes, private storage boundaries, exclusion of WAN, offline/known status, duplicate identities, and stable order.
- [x] Implement a responsive standalone frontend using the authenticated normal dispatcher, with distinct Save draft and Preview controls. Browser-check manual entry, mode switching, dragging, mobile controls, persistence and errors.
- [x] Validate a compiler experiment with actual installed nfqws2 --dry-run: mark every internal --new block, keep reserved flags/global Lua/blob definitions scoped correctly, and reject conflicting dependencies. Do not install firewall rules or start a daemon for this validation.
- [x] Review and deploy only the experimental page/module and an authenticated dispatcher hook on 87U. Preserve owner main router and all original config/resources/firewall; verify API, screenshots and cleanup of the sole owned SSH session. Save exact installation evidence privately.

Result: installed only as an experiment on 87U. Authenticated live-browser save/reload/drag/preview and mobile captures passed. Seventeen PHP/Python tests and the isolated browser suite passed. Native current+stock+fallback argument validation passed; an isolated network namespace confirmed first-match order, fallback and exclusion without changing host firewall tables or physical topology. Traffic application, general catalog-profile import, DHCP-driven runtime reconciliation, and safe migration/update integration are deliberately not enabled by this prototype.
