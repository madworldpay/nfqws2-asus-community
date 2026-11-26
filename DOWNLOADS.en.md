# Downloads

**[Build 108 for all supported platforms](https://github.com/madworldpay/nfqws2-asus-community/releases/tag/build108)**

[Install with one command](QUICKSTART.en.md#install-command). Use the table if you prefer to choose the file manually.

| Installation environment | Which package to choose |
| --- | --- |
| ASUSWRT / Merlin with Entware already installed | `nfqws2-asus_…_armv7.ipk` or `nfqws2-asus_…_aarch64-3.10.ipk`, according to the Entware architecture |
| Keenetic or Netcraze with Entware | [Choose packages](#keenetic) for your installed Entware architecture |
| OpenWrt 24.10 | `nfqws2-native_VERSION_ARCHITECTURE.ipk`, matching the exact `DISTRIB_ARCH` |
| OpenWrt 25.12 | `nfqws2-native_VERSION_ARCHITECTURE.apk`, matching the exact `DISTRIB_ARCH`; the signature is checked by the native OpenWrt installer |

The native file's extension identifies the OpenWrt series, and its name contains the architecture;
check both against `cat /etc/openwrt_release`. The ASUS model alone does not determine the package:
different firmware can run on the same model.

<a id="keenetic"></a>

## Keenetic and Netcraze

The Build 108 panel uses the stock NFQWS2 service with the zapret2 1.0.8 engine and Lua. It requires Entware and the stock `nfqws-keenetic-web` web interface version `3.0.24` or later.

To install or move from an earlier revision, run the [universal installer](README.en.md#install-command) over SSH. It verifies the packages and installs the matching pair. Run `opkg print-architecture` to find your architecture. If an entry ends in `_kn`, use the corresponding base architecture.

| Entware architecture | Panel | Engine |
| --- | --- | --- |
| `aarch64-3.10` | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-3_aarch64-3.10.ipk) | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic_1.3.3%2Bcommunity108-1_aarch64-3.10.ipk) |
| `mips-3.4` | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-3_mips-3.4.ipk) | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic_1.3.3%2Bcommunity108-1_mips-3.4.ipk) |
| `mipsel-3.4` | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-3_mipsel-3.4.ipk) | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic_1.3.3%2Bcommunity108-1_mipsel-3.4.ipk) |

Keenetic specifies MIPSEL for the KN-1711. [Keenetic's instructions for this model](https://support.keenetic.com/carrier/kn-1711/en/20980-installing-the-entware-repository-on-a-usb-drive.html).

After installing, open `http://<router-address>:90/nfqws-community/`.

## ASUS and OpenWrt

For **ASUS/Entware**, choose an IPK according to the Entware architecture:

| Entware architecture | Filename suffix |
|---|---|
| `armv7-2.6` / `armv7-3.2` | `_armv7.ipk` |
| `aarch64-3.10` | `_aarch64-3.10.ipk` |

Each IPK contains NFQWS2 and the WebUI in RU and EN. SmartDNS is installed
using a separate button in the panel. The installer
automatically selects the current package.

[SHA-256 checksums for all packages](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/SHA256SUMS).
The source archive ending in `_source.tar.gz` is available alongside the IPK files in each
release. For your installed version, choose the sources from the same release.
[Sources in the repository](source/).

[Project documentation](README.en.md#documentation).
