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

## WAN and processing arguments

Leave WAN empty to detect active interfaces automatically, or enter interface names separated by spaces. On OpenWrt use logical names such as `wan` and `wan6`.

Startup arguments contain shared Lua and blob definitions; IPSET arguments reference IP lists. Separate TCP/UDP ports with commas and use a colon for ranges: `443,3478:3481`. A port must match both capture settings and the strategy filter.

## Editor and default strategies

The editor supports visual line wrapping, which does not change the text;
actual line breaks are shown separately. A quotation mark warning points to
a possible error, but does not check whether the strategy works.

On the **nfqws2.conf** tab, the main blocks are visually separated, while
the entire configuration can still be selected and copied at once.

The **Default** button restores the default TCP, QUIC, and UDP strategies and clears
the custom block. WAN and device selection are preserved. Review the result, click
**Save**, then **Restart**. This restores strategies; it does not reset all router settings.

In **Lists**, use **+** to create a `.list` file. Enter a name using Latin letters, digits, `-` or `_`, without the extension, then reference the new list in the strategy. Custom files can be deleted after confirmation; protected lists are not offered for deletion. The file editor supports removing duplicate lines, undoing an edit and saving with **Save** or **Ctrl+S / Cmd+S**.

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
Mode supplies domain lists to the main TCP and QUIC blocks. Separate UDP blocks, the custom strategy and IP-list processing use their own filters and are not automatically restricted by this choice.
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
with its own checkbox and does not disable IPv6 in the firmware. In Only listed devices mode, an empty list for one address family leaves that family's traffic unprocessed. Adding a device's IPv4 address does not automatically select its IPv6 traffic. NFQWS2 client selection does not define
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

Select the EN / RU language and theme in the collapsible lower panel. It starts collapsed on phones; expand it for community, releases, MTProto and technical-channel links. Main actions and the version stay in the header; the version button opens update checks, while the additional menu opens separately. Changing the password applies
to the separate WebUI account and does not change the ASUS password. Enter the new password twice; the limit is 72 bytes. Saving with both fields empty disables the login prompt. The technical channel still requires a configured panel password.

Header buttons use a consistent height and wrap to fit. Settings remain scrollable in portrait and landscape; short windows, including mobile desktop mode, allow page scrolling. The expanded lower panel has a bounded height and its own scrolling. Its expansion is remembered separately for narrow and wide windows; browser zoom is allowed.

For detailed logging, enable **Debug logging**, save and restart the service. **Logs** shows the newest lines first; clearing a selected log asks for confirmation. Save information needed for troubleshooting before clearing it.

The **[restart timer and service recovery](README.en.md#service-restart)** settings are next to Restart. **[Unavailable IPs](README.en.md#unavailable-ips-on-asus)** is a separate ASUS tab.

The project is free, and reports are voluntary. Save working profiles through
**Export / share** so you can restore them yourself or share them with others.

[Project documentation](README.en.md#documentation).

## DPI Detector and reports

The **DPI Detector** header button opens the original terminal and separate **Service checks**. In the terminal, start with default tests **1, 2, 3**, save with **S**, then refresh **TXT reports** and download the required file to your PC or phone. **More → Remove DPI Detector** requires separate confirmation; deleting reports starts unchecked. Checking Facebook, YouTube or Discord makes three control HTTPS requests and downloads its own TXT with request context. [Controls and interpreting results](DPI-DETECTOR.en.md).

## Packet templates (blobs)

A blob is a ready-made data template a strategy uses to bypass a block. If a
website, video or call fails, you can try another template without replacing the
whole strategy. Results depend on your ISP.

“Packet templates” shows the current file and available alternatives. Select a
file and save settings as usual. “Upload from device” adds your own `.bin` file
(up to 256 KiB); uploading alone does not change the strategy. The package
includes 12 official zapret2 templates: 6 TLS, 5 QUIC and 1 STUN. Their names
describe the template contents, not a list of websites they unblock.
