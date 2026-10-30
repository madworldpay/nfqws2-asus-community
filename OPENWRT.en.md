# OpenWrt: installation and compatibility

The native `nfqws2-native` package uses OpenWrt's `procd`, `netifd` and
`firewall4` / `nftables`. It does not require Entware. It includes our shared
panel with strategies, device selection, local JSON and cloud presets,
import preview and undo, SmartDNS, diagnostics and updates.

## Install

Connect to **the OpenWrt router** over SSH as `root` and run:

```sh
( nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh; nfqws_file=$(mktemp) && trap 'rm -f "$nfqws_file"' 0 && { curl -fL --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_file" || uclient-fetch -T 20 -O "$nfqws_file" "$nfqws_url"; } && sh "$nfqws_file" )
```

The installer detects the OpenWrt release series and exact package architecture,
selects an IPK for OpenWrt 24.10 or APK for OpenWrt 25.12, and verifies the release
signature and SHA256. Missing prerequisites come from your configured signed
OpenWrt repositories. If they require replacing existing system packages,
the installer explains the issue; update those packages through OpenWrt first.

Processing stays off after a first install. Updates preserve settings and the
previous service state. Closing SSH after the background installation starts
does not cancel it. If installation fails, keep the log directory reported
by the installer.

To check a downloaded installer without installing the package, run
`sh install.sh --check`. If the required PHP runtime is absent, this mode lists
its prerequisites and stops without installing them.

### Choose a package manually

Check the router's exact release and architecture:

```sh
cat /etc/openwrt_release
```

Choose the file matching **both the OpenWrt series and `DISTRIB_ARCH`** and copy
it to the router's `/tmp`. For 24.10, use `opkg install /tmp/package-name.ipk`.
For 25.12, use the installer above: it prepares verification of our APK signature
separately from the system key store. ASUS/Entware and native OpenWrt packages
have different names and architectures; use the matching variant.

### Transfer a downloaded file

For an IPK, use WinSCP: select **SCP**, the router address, user `root`
and destination directory `/tmp`. Or run this **on your computer**:

```sh
scp -O "./package.ipk" root@192.168.1.1:/tmp/package.ipk
```

Replace the package name and IP with yours. Then install the OpenWrt 24.10 IPK
**in the router's SSH session**: `opkg install /tmp/package.ipk`.
For OpenWrt 25.12, retain the APK signature verification procedure described above.

If Samba/ksmbd is already configured on OpenWrt, open the USB share in File Explorer,
for example as `\\192.168.1.1\USB`, and copy the file normally.
On Linux and macOS, use `smb://192.168.1.1/USB`. Find the router's local path in
**LuCI → System → Mount Points** and the share settings.
For example, if the USB drive is mounted at `/mnt/usb`, run this **in the router's SSH session**:

```sh
cp "/mnt/usb/package.ipk" /tmp/package.ipk
```

`USB`, `/mnt/usb` and the filename are examples; the share must point to
the drive containing your copied package. A file transfer does not install anything.

## Set up the panel

1. Open the address printed by the installer, `http://router-IP:90`. The default login uses the OpenWrt `root` account. A separate panel password can be set through **Change password**.
2. Keep automatic WAN discovery or choose an OpenWrt logical interface such as `wan` or `wan6`. PPPoE devices are resolved through `netifd`.
3. Select devices and a strategy. In **Only listed devices**, `192.168.1.20` and `192.168.1.30`, one per line, select two devices. `192.168.1.0/24` selects that entire subnet. Reserve individual device addresses in **LuCI → Network → DHCP and DNS → Static leases**.
4. You can import your own JSON or a cloud preset. Everything selected by the profile author is initially selected; you can deselect unwanted parts. Review the preview and apply. Supported file paths are adapted to OpenWrt; your router's local WAN and client selection are retained instead of importing another network's addresses.
5. For domain-specific DNS, open SmartDNS, prepare a profile, test the connection and confirm it. The original `dnsmasq` configuration is retained; without confirmation, the previous DNS is restored.
6. Start NFQWS2. Check increasing packet counters, then test websites, video playback and voice from a selected client.

The panel listens on the chosen local network and leaves LuCI configuration
in place. NFQWS2 settings live in `/etc/nfqws2/`; panel settings live in
`/etc/nfqws2-web/` and `/etc/config/nfqws2-web`. Hardware acceleration and
software flow offloading can bypass NFQUEUE; the panel checks for this and
explains the necessary action.

Export and sharing follow the same workflow:
select the contents, review the preview, then download the JSON or send a report.
Share working strategies with your model, firmware and test conditions to help
other users on the same provider.

## Devices and package compatibility

The decisive values are **OpenWrt series and `DISTRIB_ARCH`**, rather than a brand
or CPU marketing name. Revisions of the same model may use different architectures.
Examples below come from the official OpenWrt device profiles. Firmware support,
Wi-Fi and port functionality depend on OpenWrt's support for the actual device.

| `DISTRIB_ARCH` | Family / examples | Our application verification |
| --- | --- | --- |
| `arm_cortex-a9` | Broadcom ARMv7: ASUS RT-AC87U, RT-AC68U, RT-AC88U | **RT-AC87U on OpenWrt 24.10: hardware verified**. Other models: **Theoretical compatibility** |
| `arm_cortex-a7_neon-vfpv4` | Qualcomm IPQ40xx: ASUS RT-AC58U, RT-ACRH17, Lyra | **Theoretical compatibility** |
| `arm_cortex-a15_neon-vfpv4` | Qualcomm IPQ806x: ASUS OnHub SRT-AC1900 | **Theoretical compatibility** |
| `aarch64_cortex-a53` | ARM64: ASUS RT-AX59U, TUF-AX4200, TUF-AX6000; devices with the same OpenWrt architecture | **Theoretical compatibility** |
| `mips_24kc` | Big-endian MIPS: ASUS RT-AC59U, ZenWiFi CD6 | **Theoretical compatibility** |
| `mipsel_24kc` | Little-endian MIPS: ASUS RT-AC65P, RT-AX53U; MediaTek/Ralink | **Theoretical compatibility** |
| `mipsel_74kc` | MIPSel: ASUS RT-N16, RT-N66U, RT-AC53U | **Theoretical compatibility** |
| `mips64_octeonplus` | Cavium/Marvell Octeon | **Theoretical compatibility** |
| `i386_pentium4` | 32-bit x86 devices using this package architecture | **Theoretical compatibility** |
| `x86_64` | 64-bit PCs, mini PCs and virtual machines running OpenWrt | **Theoretical compatibility** |

Each row has a separate IPK (24.10) and APK (25.12). The panel is shared;
engines are selected by ABI, word size, endianness and instruction set.
Build checks and isolated runtime tests do not replace testing on a specific
router. Optional tools have their own compatibility: an unavailable DPI Detector
binary does not imply that NFQWS2 itself is unsupported.

Installation requires repositories matching your OpenWrt release, `firewall4`,
kernel NFQUEUE support, and storage for the application, prerequisites and
installation staging. The installer checks space against the actual selected
package. USB or overlay expansion does not increase RAM.

Official information: [OpenWrt device catalog](https://openwrt.org/toh/start),
[firmware profiles](https://downloads.openwrt.org/releases/25.12.6/targets/).

## Commands and removal

```sh
/etc/init.d/nfqws2-native start
/etc/init.d/nfqws2-native stop
/etc/init.d/nfqws2-native status
/etc/init.d/nfqws2-native-web restart
```

`opkg remove nfqws2-native` (24.10) or `apk del nfqws2-native` (25.12) stops our
services and removes their rules while retaining user settings. It removes the
application; the OpenWrt firmware remains installed.
Native integration source: [source/project/openwrt](source/project/openwrt/).

[Project documentation](README.en.md#documentation).
