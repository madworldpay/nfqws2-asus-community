# DPI Detector

**Build 96 interface.** The original terminal is available since Build 88, TXT downloads and protected removal since Build 91, and separate Service checks since Build 96. The DPI Detector button opens the window directly in the panel. [Running over SSH](#run-over-ssh) is also supported.

DPI Detector is a separate, optional tool by [Runnin4ik](https://github.com/Runnin4ik/dpi-detector). It helps compare DNS, HTTP, TLS, QUIC and connections to network targets. NFQWS2 does not require Detector. Detector does not select or change a strategy automatically.

## Run from the panel

1. Click **DPI Detector** at the top of the panel. If it is missing, click **Install DPI Detector** and confirm. The panel checks the pinned file, SHA256 and launch. The original menu opens after installation; no separate SSH login is needed.
2. Start with tests **1, 2, 3**, selected by default. Arrow keys move the selection, **Space** toggles tests and **Enter** confirms. On a phone, use the buttons below the terminal.
3. Wait for the result and press **S** in the results menu to save the original TXT.
4. In the Detector window, refresh **TXT reports** and click download next to the required TXT to save it to your PC or phone. **Export / share** also lets you select it for sending through the preview.

The **?** button and expandable help explain installation, tests, controls and results. **Esc** goes back in the original menu; **Q** quits Detector. Closing the panel window stops its terminal and current tests. Open it again for a new run. The window contains one original terminal: status, report-list and help updates do not create copies. **Open terminal again** replaces its session. A second terminal or separate Detector check cannot run at the same time.

Scroll history with the wheel or a vertical swipe; buttons jump to the top, bottom or another page. Keyboard shortcuts are **Shift+PageUp/PageDown** and **Shift+Home/End**. Wide tables scroll horizontally without moving the whole page.

## Compare and interpret results

[Worked example: the package default and a personal DOM.RU strategy](docs/DETECTOR-COMPARISON.en.md) explains what to compare, how to import and why one connection does not represent everyone.

**Detector matters when checking an imported profile:** comparing the same tests helps distinguish DNS problems from connection, TLS or QUIC failures. For a baseline, save a result with NFQWS2 off, then turn it on and repeat the same tests. To compare two strategies, test each with the service running under the same conditions. Change one setting at a time. Account for DNS, VPNs, another bypass on the route and changing target addresses; otherwise a difference cannot reliably be attributed to the strategy.

- **DNS:** failures of plain or encrypted DNS, altered replies and unexpected resolvers help investigate a problem. The report does not prove the absence of all DNS leaks.
- **Connection:** a timeout before TCP connects, a TLS failure and an interrupted transfer are different results. A single failure does not prove ISP blocking.
- **Protocol:** HTTP, TLS and QUIC are tested separately. `—` for QUIC can mean the server does not support it; `CLOSED` means the server closed the handshake.
- **OK percentage:** covers only the selected tests. It does not guarantee every website, video, seek operation or voice call works.

**What OK means:** the original Detector judges its own network probe. A completed HTTP error response, such as **400**, may also receive OK. This does not confirm a usable page, its resources or a successful login. A normal redirect does not establish that its destination works either.

DNS availability in the original menu is an **independent check of its public resolver list**. It does not test the entire configured SmartDNS or AdGuard Home chain. An unchanged DNS-availability summary after changing a DNS profile does not by itself prove that the profile was not applied.

Test the required service from a selected device after changing a strategy. **Collect diagnostics** gathers router information and does not run Detector network tests.

## Service checks

Starting with Build 96, a separate **Service checks** view in the Detector window covers Facebook, YouTube and Discord. It supplements the original menu with HTTP status, redirect, bytes read and network errors for fixed control domains. Switching closes the window's original terminal; concurrent checks are excluded.

Select a service and click **Run service check**. Each run checks the selected service’s three URLs sequentially, from nine fixed targets in total:

| Service | Control URLs |
| --- | --- |
| Facebook | `https://www.facebook.com/`, `https://m.facebook.com/`, `https://static.xx.fbcdn.net/` |
| YouTube | `https://www.youtube.com/`, `https://i.ytimg.com/`, `https://www.gstatic.com/` |
| Discord | `https://discord.com/`, `https://cdn.discordapp.com/`, `https://gateway.discord.gg/` |

The check makes certificate-verified HTTPS requests, uses system name resolution and does not follow redirects. HTTP 400 is shown as a server error response. A connection reset differs from HTTP 403/404: a CDN root may not serve a public page. Each request is limited to 10 seconds and 256 KiB of response body, with a partial-read label when the body limit is reached; control domains do not cover every asset, video playback, voice, matches or authentication. Full service functionality is never asserted automatically.

**Download service TXT** saves the control report to your PC or phone. Every request records its times and before/after snapshots of NFQWS2 state, mode and configuration SHA256. Different known values are marked changed; incomplete observations remain unknown. Matching snapshots cannot rule out changes between them. If the router clock moves backwards, original timestamps and a warning are retained; duration uses a monotonic timer. This context belongs to the control requests, not an unrelated original-menu run. The check does not change settings, lists, DNS or service state.

This integration does not record historical NFQWS2 state, mode or configuration SHA256 in original TXT files; those values remain unknown. The panel never inserts the current service state into them or infers test start from opening the terminal. Record each run's conditions separately when comparing original TXT files.

## Reports and removal

The original TXT stays local and may contain network information. Sending prepares a separate sanitized JSON containing recognized metrics; it may be incomplete. Sending requires a preview and a separate click; tests are not run again.

**Uninstall DPI Detector** is in the window’s **More** menu and opens a separate confirmation. **Delete saved Detector reports** is unchecked by default: normal removal keeps reports. Selecting that checkbox also deletes saved reports, which cannot be restored from the panel. Cancelling confirmation does not restart the current terminal.

## Architectures

The shared interface is intended for ASUS/Entware and native OpenWrt. An NFQWS2 package for an architecture does not imply that a compatible Detector is available.

| Family | Pinned Detector variant |
| --- | --- |
| ARM64, MIPS, MIPSel, x86-64; ASUS/Entware `armv7-3.2` | Official v5.0.0-alpha.21 artifact |
| Older Entware `armv7-2.6` and native OpenWrt ARM | Compatible ARMv5TE build from the same source; the standard official ARMv7 file did not launch on the tested older RT-AC87U |
| 32-bit x86, MIPS64 | No compatible artifact is pinned; Detector installation is unavailable |

This limits Detector, not NFQWS2 or SmartDNS. Artifact support and a launch check do not replace network testing on each model.

## Run over SSH

After installing Detector, you can also open its original menu on the router:

```sh
# ASUS / Entware
/opt/bin/nfqws2-dpi

# OpenWrt
/usr/bin/nfqws2-dpi
```

Do not run it alongside the panel's Detector window. Press **S** to save TXT, then refresh the panel's result list.

[Project documentation](README.en.md#documentation).
