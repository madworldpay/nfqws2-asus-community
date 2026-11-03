# Panel screenshots

Build 85 interface. Addresses, states and example entries are demonstration values, not a report on a live connection. New sections use Build 85 components; existing images of unchanged screens are retained.

Expand a screenshot and click it for full size. Static JPEG images have no animation; collapsed sections keep the gallery compact on phones.

[Русский](SCREENSHOTS.md) · [Documentation](README.en.md)

## NFQWS2 main panel

Settings and service controls share one panel. The top bar provides start or restart, the service menu, schedule, import, export and update checks. Save becomes available after changing settings.

<details>
<summary>Show screenshot</summary>

[![NFQWS2 main panel](images/screenshots/panel-overview-en.jpg)](images/screenshots/panel-overview-en.jpg)

</details>

## Getting started

Open Getting started in the top bar for router checkup and setup steps. Checkup reports the process, queue binding, ARK presence and platform readiness. It changes nothing; test your sites from a client device after setup.

<details>
<summary>Show screenshot</summary>

[![Getting started](images/screenshots/getting-started-en.jpg)](images/screenshots/getting-started-en.jpg)

</details>

## Device selection

Settings → Devices and IPv6: process all devices, only listed devices, or all except listed devices. Separate IPv4, IPv6 and subnets with spaces. Reserve addresses in DHCP; in Only listed mode, an empty list leaves that address family unprocessed.

<details>
<summary>Show screenshot</summary>

[![Device selection](images/screenshots/devices-en.jpg)](images/screenshots/devices-en.jpg)

</details>

## Strategy catalog

Import strategies → From cloud lists provider presets and global strategies. Select a preset, then review its contents and changes before saving. A preset name does not guarantee success on every ISP; test it on your connection.

<details>
<summary>Show screenshot</summary>

[![Strategy catalog](images/screenshots/profile-catalog-en.jpg)](images/screenshots/profile-catalog-en.jpg)

</details>

## Import a Keenetic strategy

Choose Paste a Keenetic strategy in the import window. Paste NFQWS2 text and select Convert for ASUS to adapt paths and prepare a review. Check referenced lists and blobs; saving is a separate step.

<details>
<summary>Show screenshot</summary>

[![Import a Keenetic strategy](images/screenshots/keenetic-import-en.jpg)](images/screenshots/keenetic-import-en.jpg)

</details>

## Import preview

After opening a JSON file or preset, select Preview. Compare before and after, and deselect unwanted sections. Running settings change only after Save selection; apply any required restarts afterwards.

<details>
<summary>Show screenshot</summary>

[![Import preview](images/screenshots/import-preview-en.jpg)](images/screenshots/import-preview-en.jpg)

</details>

## Strategy editor

Settings → Config separates startup, TCP, QUIC, UDP and custom strategy blocks. Highlighting and visible line breaks help inspect parameters. Save changes, then restart NFQWS2 to apply the strategy.

<details>
<summary>Show screenshot</summary>

[![Strategy editor](images/screenshots/strategy-editor-en.jpg)](images/screenshots/strategy-editor-en.jpg)

</details>

## Packet templates — blobs

Expand Packet templates (blobs) below launch parameters. Select another file for an existing blob name, or upload a .bin from 1 byte to 256 KiB. Selection changes the draft: save and restart the service. A different blob may not suit the strategy.

<details>
<summary>Show screenshot</summary>

[![Packet templates — blobs](images/screenshots/blob-picker-en.jpg)](images/screenshots/blob-picker-en.jpg)

</details>

## Domain lists

Use Lists to edit domain lists and exclusions. Auto mode adds domains requiring processing to auto.list. This is separate from unavailable-IP tracking: a domain in auto.list does not establish that its IP is unavailable.

<details>
<summary>Show screenshot</summary>

[![Domain lists](images/screenshots/domain-lists-en.jpg)](images/screenshots/domain-lists-en.jpg)

</details>

## Unavailable IPs

This tab shows confirmed unavailable addresses, exclusion time and rechecks. The first incident lasts 24 hours, a repeat 7 days; three successful checks restore an address. One timeout or QUIC failure does not add an entry. DNS filtering covers ordinary UDP DNS for selected clients; DoH, DoT and TCP DNS bypass it.

<details>
<summary>Show screenshot</summary>

[![Unavailable IPs](images/screenshots/unavailable-ips-en.jpg)](images/screenshots/unavailable-ips-en.jpg)

</details>

## Scheduled restart and recovery

Use the timer icon beside the service controls: off, every 4, 12 or 24 hours, or a custom interval. Useful on devices with limited RAM. The timer restarts only a running NFQWS2 service, never the router. Enable service recovery for up to three attempts after failure with increasing delays, then it stops; a manual stop is respected. Save the chosen settings.

<details>
<summary>Show screenshot</summary>

[![Scheduled restart and recovery](images/screenshots/restart-timer-en.jpg)](images/screenshots/restart-timer-en.jpg)

[![Recovery tooltip](images/screenshots/service-watchdog-en.jpg)](images/screenshots/service-watchdog-en.jpg)

</details>

## SmartDNS: connection and restore

The SmartDNS tab shows router readiness, the DNS profile and connection state. Prepare and validate a profile, then connect and confirm the result. Restore previous DNS returns saved settings. A successful DNS response alone does not prove that a website works.

<details>
<summary>Show screenshot</summary>

[![SmartDNS: connection and restore](images/screenshots/smartdns-en.jpg)](images/screenshots/smartdns-en.jpg)

</details>

## DNS for individual sites

A SmartDNS profile assigns DoH/DoT servers to domains. Include subdomains extends the rule to matching names. Editing fields prepares a profile; connection follows validation.

<details>
<summary>Show screenshot</summary>

[![DNS for individual sites](images/screenshots/dns-rules-en.jpg)](images/screenshots/dns-rules-en.jpg)

</details>

## Fixed DNS answers

A separate rule maps a domain to specified IPs. Use it when an address is known and verified; it does not automatically discover a working server. Review the record if the service changes its addresses.

<details>
<summary>Show screenshot</summary>

[![Fixed DNS answers](images/screenshots/fixed-dns-en.jpg)](images/screenshots/fixed-dns-en.jpg)

</details>

## Diagnostics and submission contents

Export / share lets you select diagnostics, a saved DPI Detector result, strategy blocks, lists, blobs or DNS. Select all chooses materials; it does not fill in the strategy purpose. Editing a submission copy does not alter the router configuration.

<details>
<summary>Show screenshot</summary>

[![Diagnostics and submission contents](images/screenshots/diagnostics-en.jpg)](images/screenshots/diagnostics-en.jpg)

</details>

## Share a working profile

Selecting a strategy reveals Service or purpose, provider and comment fields. Describe what you tested and under which conditions. Preview prepares a review and JSON download; Send to developer is a separate action. Preview again after changing the contents or text.

<details>
<summary>Show screenshot</summary>

[![Share a working profile](images/screenshots/profile-sharing-en.jpg)](images/screenshots/profile-sharing-en.jpg)

</details>

## MTProto for Telegram — without Docker

Open MTProto for Telegram in the footer, choose Without Docker and select a device. The panel fills in the ASUS LAN address, keeps it editable, and generates a dd-secret, installer and connection link. Run installation on the selected device; it does not replace NFQWS2. A LAN link works at home; external access requires a separately configured route to the proxy.

<details>
<summary>Show screenshot</summary>

[![MTProto for Telegram — without Docker](images/screenshots/mtproto-entware-en.jpg)](images/screenshots/mtproto-entware-en.jpg)

[![Telegram connection link](images/screenshots/mtproto-link-en.jpg)](images/screenshots/mtproto-link-en.jpg)

</details>

## MTProto — Docker and Portainer

Choose With Docker, then Portainer for compose.yaml or Terminal for a command. The link uses the editable Docker host address. Save the configuration and link before closing: generating a new secret does not change an installed proxy. The installer does not open firewall ports.

<details>
<summary>Show screenshot</summary>

[![MTProto — Docker and Portainer](images/screenshots/mtproto-docker-en.jpg)](images/screenshots/mtproto-docker-en.jpg)

</details>

## Temporary technical channel

The footer button opens a field for an administrator invitation link. Arrange access beforehand: the administrator can run router commands during the session. Access expires, can be disconnected manually, and does not resume after reboot.

<details>
<summary>Show screenshot</summary>

[![Temporary technical channel](images/screenshots/technical-channel-en.jpg)](images/screenshots/technical-channel-en.jpg)

</details>

## Updates in the panel

Check for updates in the top bar shows installed and available builds with changes between them. Preparation downloads and verifies the package. Installation records service states, stops services during replacement, then restores their previous states. Recovery runs on failure. A previously stopped service should remain stopped.

<details>
<summary>Show screenshot</summary>

[![Updates in the panel](images/screenshots/updates-en.jpg)](images/screenshots/updates-en.jpg)

</details>

[Project documentation](README.en.md#inside-the-panel).
