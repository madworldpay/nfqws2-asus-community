# SmartDNS

The SmartDNS wizard is available on ASUS/Entware and OpenWrt. The description of the `dnsmasq.postconf` hook and `/opt` paths below applies to ASUS/Entware; native OpenWrt uses its own dnsmasq integration.

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
5. Click **Check profile**, then **Connect**.
6. Check DNS from a device and click **DNS works — keep settings**.

**Check profile** checks the settings and whether the configuration starts; it does not
change the server selection. During connection, a general DNS response is checked. You then
have **120 seconds** to check sites from a device and confirm the result.
Without confirmation, the protection mechanism restores the previous DNS.

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

After an update, the package tries to restore the previously confirmed profile,
even if the editor already contains a different draft. The draft is preserved.
Explicitly restoring the previous DNS cancels automatic restoration.
If the connection fails or another service changes the DNS path, the panel shows guidance.

A browser's built-in DoH, a phone's Private DNS, or DNS inside a VPN may bypass
the router's DNS. Check the actual query path when results differ.

If DNS is part of a successful profile, select it together with the strategy in
**Export / share**, check the preview, and send the result to the project.
This helps reproduce the result on another network.

[Project documentation](README.en.md#documentation).
