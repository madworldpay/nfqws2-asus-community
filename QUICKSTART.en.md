# Quick start

## ASUSWRT-Merlin / Entware

For a router with ASUSWRT-Merlin, SSH and working Entware in `/opt`.

### 1. Install

Connect to **the router** over SSH and paste this command:

```sh
( nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh; nfqws_file=$(mktemp) && trap 'rm -f "$nfqws_file"' 0 && { curl -fL --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_file" || wget --https-only -T 20 -t 2 -O "$nfqws_file" "$nfqws_url"; } && sh "$nfqws_file" )
```

It selects the current IPK for your Entware architecture, verifies SHA256
and installs the package while preserving settings. After a first install,
processing stays off; updates retain the previous state. The panel address is printed at the end.

You need `curl` or GNU `wget`. Install Entware beforehand.

### 2. Configure

1. Open `http://ROUTER_IP:90` and sign in with your ASUS administrator credentials.
   If the panel could not read them, the fallback login is `root` / `asus`.
   Use **Change password** to set a separate panel password.
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
( nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh; nfqws_file=$(mktemp) && trap 'rm -f "$nfqws_file"' 0 && { curl -fL --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_file" || uclient-fetch -T 20 -O "$nfqws_file" "$nfqws_url"; } && sh "$nfqws_file" )
```

The installer selects a native package for your OpenWrt version and architecture,
verifies the signature and SHA256, then prints the panel address.

1. Open `http://ROUTER_IP:90`. The default login uses the OpenWrt `root` account; you can change the panel password separately.
2. Keep automatic WAN selection. Select devices and a strategy, or import a cloud profile. Review the preview, save settings and start NFQWS2.
3. If the profile includes DNS, open SmartDNS: **Install → Check profile → Connect → confirm the result**.
4. Test the required services from a selected device. If the panel warns about traffic acceleration, follow its flow offloading guidance.

Reserve selected device addresses in **LuCI → Network → DHCP and DNS → Static leases**.
To stop, use the panel button or `/etc/init.d/nfqws2-native stop`;
to restore DNS, use **Restore previous DNS** in SmartDNS.

[Device compatibility and OpenWrt specifics](OPENWRT.en.md).

[Project documentation](README.en.md#documentation).
