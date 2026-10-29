# Manual IPK installation

For ASUSWRT-Merlin with Entware already installed. This guide covers the full manual installation procedure.

## 1. Choose a package

In the router's SSH session, check the architecture:

```sh
/opt/bin/opkg print-architecture
```

| Entware architecture | Package |
|---|---|
| `armv7-2.6` / `armv7-3.2` | ARMv7 |
| `aarch64-3.10` | AArch64 |

Download the appropriate IPK and `SHA256SUMS` from the [current release](https://github.com/madworldpay/nfqws2-asus-community/releases/latest).
Check the downloaded file on your computer: in Windows PowerShell, use
`Get-FileHash .\filename.ipk -Algorithm SHA256`; in Linux, use `sha256sum filename.ipk`.
Replace `filename.ipk` with the name of the downloaded IPK.
Compare the result with the entry for that file in `SHA256SUMS`.

## 2. Transfer it to the router

Prepare a directory on the Entware drive:

```sh
mkdir -p /opt/tmp
```

On Windows, transfer the verified file using WinSCP as `/opt/tmp/nfqws2-asus.ipk`.
For the built-in ASUS SSH server, select the SCP protocol.

## 3. Install

For a **first installation**, run the following in the router's SSH session:

```sh
/opt/bin/opkg update
NFQWS_ASUS_NO_START=1 /opt/bin/opkg install /opt/tmp/nfqws2-asus.ipk
```

Traffic processing will remain disabled until configured. The same command also works for
an update when you want to leave the service disabled.

To update **and start NFQWS2 after installation**, use:

```sh
/opt/bin/opkg install /opt/tmp/nfqws2-asus.ipk
```

A regular `opkg install` attempts to start the service after installation. To
preserve its previous state automatically, use
**“Update” → “Prepare package” → “Install update”** in the panel.
Dependencies are downloaded from Entware. If an error occurs, save the installation output for diagnostics.

## 4. Open the panel

Open `http://ROUTER_IP:90` and sign in with your ASUS administrator credentials.
Follow the ARK check prompts, select devices and a strategy, save the settings,
and start NFQWS2. If you need SmartDNS, connect it using the separate wizard and confirm DNS.

OpenWrt uses a native package: [manual selection and installation](OPENWRT.en.md#choose-a-package-manually).

[Project documentation](README.en.md#documentation).
