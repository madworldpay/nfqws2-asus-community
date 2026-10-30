# Quick start

## ASUSWRT-Merlin / Entware

For a router running ASUSWRT-Merlin.

### 1. Install

**If Entware is already working in `/opt`, continue with the installation command.**
On a fresh ASUSWRT-Merlin installation, prepare Entware first:

1. Connect a USB drive with a Linux filesystem — normally ext4; ext2/ext3 also work. Save any files you need before formatting the drive.
2. Enable SSH for the local network under **Administration → System**, then connect to the router using your ASUS administrator account.
3. Run `amtm` over SSH, choose `ep` and wait for Entware installation to finish.
4. Press `e`, then Enter, to leave `amtm` and return to the same SSH shell. Check Entware with `/opt/bin/opkg print-architecture`.

Paste the complete command into that same SSH shell:

```sh
(
  set -e
  umask 077
  nfqws_dir=/tmp/nfqws2-install.$$
  mkdir "$nfqws_dir"
  trap 'rm -rf "$nfqws_dir"' 0
  curl -fL --connect-timeout 10 --max-time 60 \
    https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh \
    -o "$nfqws_dir/install.sh"
  sh "$nfqws_dir/install.sh"
)
```

It selects the current IPK for your Entware architecture, verifies SHA256
and installs the package while preserving settings. After a first install,
processing stays off; updates retain the previous state. The panel address is printed at the end.

The command uses `curl` supplied with Merlin.

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

## OpenWrt

For a router running OpenWrt. Entware is not required.
Connect to the router over SSH as `root` and run:

```sh
(
  umask 077
  nfqws_dir=/tmp/nfqws2-install.$$
  mkdir "$nfqws_dir" || exit 1
  trap 'rm -rf "$nfqws_dir"' 0
  nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh
  { curl -fL --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_dir/install.sh" || uclient-fetch -T 20 -O "$nfqws_dir/install.sh" "$nfqws_url"; } &&
  sh "$nfqws_dir/install.sh"
)
```

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
