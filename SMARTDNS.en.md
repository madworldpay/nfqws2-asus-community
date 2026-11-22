# SmartDNS

The SmartDNS wizard is available on ASUS/Entware and OpenWrt. The description of the `dnsmasq.postconf` hook and `/opt` paths below applies to ASUS/Entware; native OpenWrt uses its own dnsmasq integration.

## Current DNS and returning to the previous route

**DNS in use** shows addresses read from the router's current DNS configuration,
separate domain routes and explicit DHCP DNS options. When SmartDNS is connected,
it also lists resolvers, protocols and addresses from the **active profile**.
Editing a draft does not switch the DNS that is currently connected.

Router DNS and device DNS can differ. For example, DHCP can send devices to
AdGuard at a separate LAN address, while AdGuard uses the router with SmartDNS.
Manual settings, a VPN or browser secure DNS can choose a different path.
Reconnect devices after changing DHCP DNS so they receive the new settings.
A configuration snapshot does not verify every DNS query; unreadable sources are
shown as unknown rather than assigned an assumed resolver.

To disconnect the profile, use **Restore previous DNS** on the same page.
Wait for the result and check the updated addresses under **DNS in use**.
This removes our forwarding; it does not change manual device DNS or ASUS
**LAN → DHCP Server** fields. If you changed those separately, restore their
saved previous values there. A conflict message means restoration has not been
confirmed; keep the message and do not assume DNS has been restored.

## What it is for

**SmartDNS is a separate utility, not a built-in ASUS feature.**
In our setup, SmartDNS handles “site → selected DoT/DoH” rules
and fixed responses. The NFQWS2 panel installs and configures it.
This brings the per-site DNS setup familiar to Keenetic users to ASUS.

DNS returns a site's IP address. Different DNS servers may select different CDN addresses,
where the same strategy may behave differently. SmartDNS lets you:

- assign separate DoT/DoH servers to specific sites;
- choose DNS for other sites;
- pin a domain to an IP address if a tested profile requires it.

To use these features, install SmartDNS through our panel. It helps
obtain the required site addresses, while NFQWS2 processes connections to them.
If a strategy's result depends on DNS, transfer them together: the same strategy
with different addresses may produce a different result. A fixed IP address may become outdated.

## Encrypted DNS and checking leaks

DoT and DoH encrypt queries between SmartDNS and the selected resolver. Plain
UDP/TCP DNS sends them unencrypted: entering `8.8.8.8` alone does not enable
encryption. Check the **protocol**, default resolvers and site assignments.
Multiple DoT/DoH options let you choose reachable resolvers and different CDN
answers; the suitable choice depends on your network. [SmartDNS protocols](https://pymumu.github.io/smartdns/en/config/basic-config/).

**Adding DoH does not disable plain DNS entries in the profile.** A UDP/TCP
resolver also selected as **Default** or assigned to a site still permits
an unencrypted path for those queries. Review the entire profile, including fallbacks.

If you do not use SmartDNS, supported ASUS firmware offers stock
**WAN → Internet Connection → DNS Privacy Protocol → DNS-over-TLS**.
Set the resolver and certificate hostname using the [official ASUS instructions](https://www.asus.com/us/support/faq/1051428/).
Stock DoH availability depends on firmware; these instructions cover DoT.

Also check client DNS, IPv6, VPNs and fallback resolvers: some queries may follow
a different path. Detector's DNS test directly queries public resolvers,
including over UDP; distinguish its results from the actual path of ordinary
device queries. Google appearing in that test alone is not proof of a leak.

Change one setting at a time and compare repeated measurements and the service
you need. DoT/DoH keep your public IP unchanged and do not guarantee a different
region or lower ping. Changing resolvers can change CDN answers and latency.

## Using SmartDNS with XrayUI

If SmartDNS refuses to connect after XrayUI starts, save the exact panel check
message. One confirmed cause is another script recreating the shared
`dnsmasq.postconf` with write permission for everyone (`0777`). The SmartDNS
safety check rejects that script.

For a permission error, click **“Fix permissions and retry the check”**. For a regular
root-owned script with mode `0777`, the panel saves a backup, sets `0755` and
validates the profile again. Addon commands, ownership and DNS stay unchanged.
The button leaves files with other owners or modes untouched. If an addon
recreates the file again, the repair may need to be repeated.

Check the shared script's owner, permissions and contents together: it may
contain commands from several add-ons. Having XrayUI installed alone does not
establish this cause; behavior depends on its version and the firmware. If the
permissions are correct, investigate the specific message and DNS state,
including any rollback result. Bring the saved log to the
[community chat](https://t.me/nfqws2AsusCommunityChat).

## How much you can add

In one profile in our panel:

- up to **32 DNS servers** in total: DoT, DoH, plain UDP, or TCP;
- up to **256 “domain → DNS” mappings** across all servers; one domain assigned to two DNS servers counts as two mappings;
- up to **64 fixed responses**, with up to **8 IP addresses** in each.

Subdomains can be included. The total profile size is limited to **64 KiB**, so
you may not be able to reach all limits at once. These are limits of the current
panel, not of the SmartDNS utility itself.

## Set up through the panel

1. Open the **SmartDNS** tab. The health check shows the installation requirements.
2. Click **Install SmartDNS** if the engine is not installed yet.
3. Select DoT/DoH from the list or enter your own. Specify sites for a separate DNS server.
   **Default** means DNS for sites without a separate assignment.
4. If needed, add a **fixed response** — a domain and a specific IP address.
5. Click **Check profile**. Review the default resolvers, domain assignments and complete configuration, then click **Connect**.
6. Check DNS from a device and click **DNS works — keep settings**.

Select at least one **Default** resolver. A custom resolver hostname needs connection IPs in bootstrap; DoT/DoH need a certificate name, and DoH also needs its full HTTPS URL. Bootstrap contains resolver addresses rather than website addresses; certificate verification stays enabled.

Fixed answers take priority over resolver selection for overlapping domains; the preview identifies these overlaps. Fixed IP records can include an optional last-checked date.

The editor first loads the saved draft. After import, it picks up the new profile while there are no unsaved manual edits; save or discard such edits before switching to imported data. Validation and preview use the server-saved, normalized profile rather than stale form contents.

Installing the engine and validating a profile do not switch DNS. Checkup reads router state without testing website access. If SmartDNS is already managed outside the wizard, drafts can be validated, but connection remains blocked until management is transferred.

**Check profile** checks the settings and whether the configuration starts; it does not
change the server selection. During connection, a general DNS response is checked. You then
have **120 seconds** to check sites from a device and confirm the result.
Without confirmation, the protection mechanism restores the previous DNS. Protection continues on the router if the window closes; reopening shows the current state.

You can use preset DoT/DoH settings or your own server. If an individual
site does not open, check the response from its assigned DNS and the service itself:
successful connection in the wizard does not replace checking each domain.

## How it connects to Merlin

The stock **dnsmasq keeps running**: DHCP and local names are preserved.
External queries are forwarded to local SmartDNS on a separate port.
The panel uses `dnsmasq.postconf` so the rule persists after DNS restarts.
This is a Merlin service script, not a kernel module or ARK preparation.

Merlin's support for custom JFFS scripts is used for this.
Existing third-party commands are preserved. Connecting SmartDNS and preparing ARK are
separate actions: ARK is checked for NFQWS2 traffic processing.
Guest networks, SDN, and VPNs may use a separate DNS path.

Connection takes standard VPN DNS configuration files into account: `ipset` rules,
local names, and client parameters are preserved. The original VPN files are not changed.
If the connection method is incompatible, the panel explains why before switching.
The **SmartDNS connected** status checks both the process and dnsmasq query forwarding.

## Restore and update

Click **Restore previous DNS**. First, the previous dnsmasq path is restored,
then our SmartDNS process is stopped. The draft remains available for further configuration.
Do not stop the only DNS server before restoring forwarding.

Before replacing a connected profile, select **Restore previous DNS**, edit the retained draft, validate and connect it again. **Load last confirmed profile** helps recover the previous working profile.

On ASUS, an administrator can check state over SSH with `/opt/bin/nfqws2-smartdns-control status` or restore DNS with `/opt/bin/nfqws2-smartdns-control rollback`.

After an update, the package tries to restore the previously confirmed profile,
even if the editor already contains a different draft. The draft is preserved.
Explicitly restoring the previous DNS cancels automatic restoration.
If the connection fails or another service changes the DNS path, the panel shows guidance.

A browser's built-in DoH, a phone's Private DNS, or DNS inside a VPN may bypass
the router's DNS. Check the actual query path when results differ.

The original DPI Detector DNS test independently queries its own public UDP/DoT/DoH resolver list. Its percentage does not verify the entire SmartDNS chain or client DNS. Service checks use router system name resolution for their URLs. [How these checks differ](DPI-DETECTOR.en.md).

If DNS is part of a successful profile, select it together with the strategy in
**Export / share**, check the preview, and send the result to the project.
This helps reproduce the result on another network.

[Project documentation](README.en.md#documentation).
