# Downloads

**[Build 108 for all supported platforms](https://github.com/madworldpay/nfqws2-asus-community/releases/tag/build108)**

[Install with one command](QUICKSTART.en.md#install-command). Use the table if you prefer to choose the file manually.

| Installation environment | Which package to choose |
| --- | --- |
| ASUSWRT / Merlin with Entware already installed | `nfqws2-asus_…_armv7.ipk` or `nfqws2-asus_…_aarch64-3.10.ipk`, according to the Entware architecture |
| Keenetic or Netcraze with Entware | [Choose the panel IPK](#keenetic) for your installed Entware architecture |
| OpenWrt 24.10 | `nfqws2-native_VERSION_ARCHITECTURE.ipk`, matching the exact `DISTRIB_ARCH` |
| OpenWrt 25.12 | `nfqws2-native_VERSION_ARCHITECTURE.apk`, matching the exact `DISTRIB_ARCH`; the signature is checked by the native OpenWrt installer |

The native file's extension identifies the OpenWrt series, and its name contains the architecture;
check both against `cat /etc/openwrt_release`. The ASUS model alone does not determine the package:
different firmware can run on the same model.

<a id="keenetic"></a>

## Keenetic and Netcraze

The Build 108 panel installs alongside the stock web interface. It requires Entware, `nfqws2-keenetic` version `1.3.3` and `nfqws-keenetic-web` version `3.0.24` or later. Installation preserves the stock service configuration. [Stock NFQWS2](https://github.com/nfqws/nfqws2-keenetic) · [Stock web interface](https://github.com/nfqws/nfqws-keenetic-web).

Run `opkg print-architecture` in the Entware terminal. Find your architecture in the table and download its package. A vendor entry such as `aarch64-3.10_kn` can appear alongside the base architecture. Use the package for the matching base entry, in this case `aarch64-3.10`.

| Entware architecture | Build 108 package |
| --- | --- |
| `aarch64-3.10` | [Download ARM64](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-2_aarch64-3.10.ipk) |
| `mips-3.4` | [Download MIPS](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-2_mips-3.4.ipk) |
| `mipsel-3.4` | [Download MIPSEL](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-2_mipsel-3.4.ipk) |

Keenetic specifies MIPSEL for the KN-1711. [Keenetic's instructions for this model](https://support.keenetic.com/carrier/kn-1711/en/20980-installing-the-entware-repository-on-a-usb-drive.html).

Check the SHA-256 digest, copy the IPK to the router and open its directory. Run `opkg install ./filename.ipk` with the downloaded filename. Then open `http://<router-address>:90/nfqws-community/`. [Release, checksums and source code](https://github.com/madworldpay/nfqws2-asus-community/releases/tag/build108).

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
