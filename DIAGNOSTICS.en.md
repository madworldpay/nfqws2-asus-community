# Diagnostics

Check traffic from the selected device and the service status in the panel.
To check over SSH, use the command for your platform:

```sh
# ASUS / Entware
/opt/etc/init.d/S51nfqws2 status

# OpenWrt
/etc/init.d/nfqws2-native status
```

**Getting started** shows the health check and unfinished steps.
**ARK check** helps prepare ASUS if the module interferes with packet delivery.

ARK is a traffic processing module in some ASUS firmware. Certain
QoE, filtering, and blocking features are associated with it. A loaded ARK module can prevent packets
from reaching NFQUEUE — the mechanism through which NFQWS2 receives traffic. In that case, the NFQWS2
process is running, but no packets arrive for processing and bypass does not work.
Preparation saves a backup and disables the related features; you then need to
reboot ASUS manually to check operation without the loaded module.

**ARK not present — no preparation required** is a normal result for firmware without ARK. Continue to strategy setup; you do not need to disable features that are absent.
An unknown internal flag alone does not prove a fault. A loaded
ARK module is shown separately; if preparation has been completed, follow the guidance to
reboot manually and check again.

| What you see | What to check |
|---|---|
| No process | Startup log, kernel capabilities, and selected WAN |
| Process is running, but the queue does not grow | Client, traffic path, new connections, and ARK |
| Some sites work, others do not | Strategy, DNS/CDN, IPv4/IPv6, and protocol |
| Results differ between the client and router | Different traffic sources and VPNs |
| Names no longer resolve after DNS setup | SmartDNS status and restoring the previous DNS |
| Panel shows regular DNS instead of SmartDNS | Whether the profile is connected and forwarding remains in place after a VPN or another service starts |
| Update did not finish | Error text and `opkg status nfqws2-asus`; then the guidance on DNS restoration |
| Results did not change after import | Whether the selected items were saved and NFQWS2 was restarted; DNS is connected separately |

The queue check confirms reception only when the counter grows within the same queue
lifetime. Repeat the check after a service restart or when evidence is unavailable.
This does not confirm that a site, video, or voice connection works; open the service itself.

## Technical channel

After arranging a session with the Administrator, open **Technical channel** at the bottom
of the panel, paste the complete invitation link and click **Connect**. Wait for
**Waiting for the Administrator**. Separate PowerShell or PuTTY commands are not needed.
Sign in with a configured panel password. **Disconnect channel** closes access; access
also ends at expiry and after a reboot.

If connection fails, save the error text before retrying. Tell the Administrator whether
a VPN runs on the computer or router; switching it during the session may interrupt access.

## Save information

1. Open **Export / share** and select **Router diagnostics**.
2. Click **Collect diagnostics** and wait for the JSON file name to appear.
3. Open **Preview**, check the contents, then select **Download JSON**
   or **Send**. The service and provider fields are not needed for diagnostics alone.

Selecting the checkbox alone does not collect diagnostics. This is information about the router's state;
DPI tests are run separately. Nothing is sent automatically.
Save the data before restarting: signs of the failure may disappear afterward.

To check whether packets are arriving, run **Check packets arriving in NFQUEUE (10 s)**
in the health check and open the service from the selected client while it runs. If
you are testing from the router itself, account for its WAN address and device selection mode.

If speeds are low, include the service, video quality, and buffering/seeking behavior
in your comment. State whether a VPN is enabled and which device runs it.
For a comparison after changing the strategy, reopen the application or browser
to create new connections.

For a more detailed check, open **DPI Detector**, install the utility,
and run the command shown by the panel. Save the result with **S**,
then click **Refresh results** in the panel.

If the submission channel is not configured yet, click **Connect sending**. Then prepare the preview and click **Send**. Connecting the channel alone does not send anything; saving JSON is available separately.

[Project documentation](README.en.md#documentation).
