# Using the panel

Panel actions are the same on ASUS/Entware and OpenWrt.

Open `http://ROUTER_IP:90`. **Getting started** shows the setup sequence
and the status of each step. **?** explains a field or action.

## Sections and applying settings

- **Settings** — WAN, devices, strategy, and processing options.
- **Lists** — files used by strategies.
- **SmartDNS** — DNS for all sites and individual domains.
- **Logs** — service messages.

Save your changes and restart NFQWS2 to apply the strategy.
The saved configuration and the running process are separate states: after editing
the strategy, use **Restart**. SmartDNS has its own connection wizard.

## Editor and default strategies

The editor supports visual line wrapping, which does not change the text;
actual line breaks are shown separately. A quotation mark warning points to
a possible error, but does not check whether the strategy works.

On the **nfqws2.conf** tab, the main blocks are visually separated, while
the entire configuration can still be selected and copied at once.

The **Default** button restores the default TCP, QUIC, and UDP strategies and clears
the custom block. WAN and device selection are preserved. Review the result, click
**Save**, then **Restart**. This restores strategies; it does not reset all router settings.

## Mode: Auto, List, and All

The **Mode** field determines which domains are processed.
It is independent of **Process traffic**, which selects devices.

| Mode | What is processed | Example use |
| --- | --- | --- |
| **List** | Domains from the custom `user.list` | You have added the domains you need and want to process only those |
| **Auto** | The custom list and domains automatically added to `auto.list` when problems are detected; domains in `exclude.list` are excluded | You also want the list to grow based on connection results |
| **All** | All traffic matching the settings, except domains in `exclude.list` | You want processing without restricting it to the custom domain list |

**Auto does not select a bypass strategy automatically.** It maintains an automatic list;
the strategy itself must suit your connection. Automatic detection
does not guarantee that every block will be recognized.

The selected mode does not override TCP/UDP port settings, protocols, or strategy filters.
Individual blocks in an imported profile may also contain their own filters.
**All does not mean all devices:** if only a TV is selected, this mode
applies to the TV's matching traffic.

## Devices and the router's own traffic

In **Process traffic**, choose which devices NFQWS2 works for:

| Panel selection | Result |
| --- | --- |
| **All devices** | Processes all clients whose traffic passes through the configured router |
| **Only listed devices** | Processes only the added IP addresses or subnets; other devices pass through without NFQWS2 processing |
| **All except listed devices** | Excludes the added IP addresses or subnets; other devices are processed |

You can add a phone, TV, PC, set-top box, or another device by its
local IP address. For example, **Only listed devices** with two addresses
enables processing only for those two devices. In exclusion mode, the same
addresses instead remain without NFQWS2 processing. This does not disable their internet access.

IPv4 and IPv6 are selected separately; the package's IPv6 processing is enabled
with its own checkbox and does not disable IPv6 in the firmware. NFQWS2 client selection does not define
the scope of SmartDNS: its profile is connected separately.

In **Only listed devices** mode, enter, for example, the following in the IPv4 field:

- `192.168.1.100` — one device.
- `192.168.1.100 192.168.1.120` — two devices, with addresses separated by a space.
- `192.168.1.0/24` — the entire specified subnet, if you want to select all of it.

Use the local IPv4 addresses of the required devices from your router's client list;
quotation marks and commas are not needed. In the DHCP server settings, reserve each IPv4 address
for the corresponding device's MAC address so that it stays the same after
reconnecting. The examples in the hint do not fill in the field automatically.

The router's own WAN addresses appear below the IPv4 clients. These are its interface addresses,
which are not necessarily public IP addresses. In selected-client mode, you can add a WAN address
if you need to process the ASUS router's own traffic. Check VPNs and guest networks separately.

EN / RU changes the language. Select the theme in the top menu. Changing the password applies
to the separate WebUI account and does not change the ASUS password.

The project is free, and reports are voluntary. Save working profiles through
**Export / share** so you can restore them yourself or share them with others.

[Project documentation](README.en.md#documentation).
