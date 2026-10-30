# DPI Detector

The panel shows the command for your system: `/opt/bin/nfqws2-dpi` on ASUS/Entware or `/usr/bin/nfqws2-dpi` on OpenWrt. Availability of the original DPI utility depends on the architecture.

This is optional network diagnostics run from the router itself. It is not required for
NFQWS2 to work and does not replace testing from a client device.

Start a new test over SSH. In **Export / share**, select an already
saved result. **Collect diagnostics** gathers information about the router
and does not run DPI tests.

1. Open **Export / share** and install DPI Detector.
2. Over SSH on the router, launch the original menu:

```sh
/opt/bin/nfqws2-dpi
```

3. Select the checks you need. In the original menu, press **S** to save a TXT file.
4. Click **Refresh results** in the panel. You can view the result,
   download it, or select it for sending through the preview.

The original TXT stays local and may contain network information.
A separate sanitized JSON is prepared for sending, containing recognized metrics;
it may be incomplete. Tests are not run again for this.

DNS, VPNs, NFQWS2, and routes affect the results. A test from the ASUS router itself may take
a different path from a phone or PC. Compare the same targets under the same conditions.

In **Only listed devices** mode, add the router's WAN IPv4 address to the processing selection
to test its own outgoing traffic. In **All devices** mode,
this is usually already covered. The **?** hint next to DPI shows how to check the route's
source address. Testing from a phone or PC remains a separate measurement.

When reading the report, check the protocol: HTTP, TLS, and QUIC are tested separately.
`—` for QUIC may mean the server does not support it; `CLOSED` means the server
responded but closed the handshake. Assess video and voice in the application itself,
and use the report to investigate why results differ.

A compatible build from the same source is provided for `armv7-2.6`:
the standard official ARMv7 binary did not run on the tested 87U.
This is specific to the DPI Detector binary, not a restriction on NFQWS2 or SmartDNS.
[Original project](https://github.com/Runnin4ik/dpi-detector).

[Project documentation](README.en.md#documentation).
