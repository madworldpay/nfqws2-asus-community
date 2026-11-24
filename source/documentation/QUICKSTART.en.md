# Quick start

<a id="install-command"></a>

## Install with one command

Paste this block into the router’s SSH shell. The same command selects the package for ASUS with Entware, Keenetic or Netcraze with Entware, and native OpenWrt.

On ASUS and KeeneticOS, prepare Entware first. The steps for each family are below.

```sh
(
  umask 077
  nfqws_dir=/tmp/nfqws2-install.$$
  mkdir "$nfqws_dir" || exit 1
  trap 'rm -rf "$nfqws_dir"' 0
  nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh
  if [ -x /opt/bin/opkg ]; then
    PATH=/opt/bin:$PATH
    if ! command -v curl >/dev/null && ! command -v uclient-fetch >/dev/null; then
      /opt/bin/opkg update && /opt/bin/opkg install curl ca-bundle || exit 1
    fi
  fi
  { curl -fL --proto '=https' --proto-redir '=https' --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_dir/install.sh" ||
    uclient-fetch -T 20 -O "$nfqws_dir/install.sh" "$nfqws_url"; } &&
  sh "$nfqws_dir/install.sh"
)
```

## ASUSWRT-Merlin / Entware

For a router running ASUSWRT-Merlin.

### 1. Install

**If Entware is already working in `/opt`, continue with the installation command.**
On a fresh ASUSWRT-Merlin installation, prepare Entware first:

1. Connect a USB drive with a Linux filesystem — normally ext4; ext2/ext3 also work. Save any files you need before formatting the drive.
2. Enable SSH for the local network under **Administration → System**, then connect to the router using your ASUS administrator account.
3. Run `amtm` over SSH, choose `ep` and wait for Entware installation to finish.
4. Press `e`, then Enter, to leave `amtm` and return to the same SSH shell. Check Entware with `/opt/bin/opkg print-architecture`.

[Run the common installation command](#install-command) in that SSH shell. On ASUS, first installation leaves processing off. Updates preserve the previous service state.

**Manual installation:** instead of the command above, download the IPK and transfer it
using WinSCP/SCP or copy it into a USB network share through Samba.
[Step-by-step transfer and installation, including Windows File Explorer](MANUAL-INSTALL.en.md).

### 2. Configure

**ASUS panel login:** use your router administrator username and password.
If the panel cannot read the ASUS system credentials, it automatically enables the
fallback login: **username `root`, password `asus`**.
A separate panel password set earlier is preserved during updates; use that password.
Use **Change password** to set your own panel password.

1. Open `http://ROUTER_IP:90`.
2. **ARK check**: if ARK is absent, no preparation is needed — continue. If the module is loaded, follow the preparation steps with a backup and manual reboot. If the module is not loaded, skip this step.
3. Keep automatic WAN selection or choose an interface, select devices and a strategy, or import JSON or a cloud preset. Click **Save**. The default configuration uses AUTO.
4. For site → DNS rules, install the separate utility: **SmartDNS → Install → choose DNS servers and sites → Check profile → Connect → confirm**.
5. Start or restart NFQWS2. Test the required services from a selected client.

**Getting started** shows completed and unfinished setup steps. **?** explains fields.
Share a working profile through **Export / share → Preview → Send**.

### 3. If you need to roll back

Save diagnostics first. In SmartDNS, click **Restore previous DNS**;
to stop traffic processing, run:

```sh
/opt/etc/init.d/S51nfqws2 stop
```

## Keenetic and Netcraze

On Keenetic or Netcraze, enable the OPKG component, select the Entware drive and wait for Entware to finish installing. Open the Entware SSH shell as `root`. The installer checks the firmware and Entware architecture, installs the matching panel and prints its address. The panel uses the stock NFQWS2 service. [Run the common installation command](#install-command). Open `http://<router-address>:90/nfqws-community/` on your LAN.

On a fresh installation the command verifies the stock IPKs and stages them in a temporary directory to preserve ownership of existing Entware directories. If the stock engine and web interface already meet the version requirements, only the community panel is installed.

## OpenWrt

For a router running OpenWrt. Entware is not required.
Connect over SSH as `root` and [run the common installation command](#install-command).

The installer selects a native package for your OpenWrt version and architecture,
verifies the signature and SHA256, then prints the panel address.

For manual file selection, use the [OpenWrt procedure](OPENWRT.en.md#choose-a-package-manually).

1. Open `http://ROUTER_IP:90`. The default login uses the OpenWrt `root` account; you can change the panel password separately.
2. Keep automatic WAN selection. Select devices and a strategy, or import a cloud profile. Review the preview, save settings and start NFQWS2.
3. If the profile includes DNS, open SmartDNS: **Install → Check profile → Connect → confirm the result**.
4. Test the required services from a selected device. If the panel warns about traffic acceleration, follow its flow offloading guidance.

Reserve selected device addresses in **LuCI → Network → DHCP and DNS → Static leases**.
To stop, use the panel button or `/etc/init.d/nfqws2-native stop`;
to restore DNS, use **Restore previous DNS** in SmartDNS.

[Device compatibility and OpenWrt specifics](OPENWRT.en.md).

[Project documentation](README.en.md#documentation).
