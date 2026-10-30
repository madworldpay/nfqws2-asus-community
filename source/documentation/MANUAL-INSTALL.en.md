# Manual IPK installation

For ASUSWRT-Merlin with Entware already installed. Download the package to your
computer, transfer it to the router and install it over SSH.
Use WinSCP/SCP or copy it to a USB drive through Samba in your normal file manager.

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

The following steps call the transferred copy `nfqws2-asus.ipk`.
You can rename it during the transfer; choose the correct package architecture first.

## 2. Transfer it to the router

Choose **one** of the methods below. Prepare a directory on the Entware drive
by running this **in the router's SSH session**:

```sh
mkdir -p /opt/tmp
```

### Using WinSCP

1. Open WinSCP on your computer. Select **SCP** for the built-in ASUS SSH server.
2. Enter the router's local IP, SSH port and the account you use for SSH.
   The examples use `192.168.1.1`, port `22` and user `admin`; substitute your own values.
3. Open `/opt/tmp` in the right pane and the folder containing the downloaded IPK in the left pane.
4. Drag the verified file to the right pane and name the copy `nfqws2-asus.ipk`.

The resulting path on the router is `/opt/tmp/nfqws2-asus.ipk`.

### Using SCP from your computer

In PowerShell or a terminal **on the computer** containing the package:

```sh
scp -O "./package.ipk" admin@192.168.1.1:/opt/tmp/nfqws2-asus.ipk
```

Replace `./package.ipk` with the downloaded file's path, and use your own router address and login.
For a different SSH port, add, for example, `-P 2222` before the file path.
In modern OpenSSH clients, `-O` selects SCP instead of SFTP,
which may be absent from the built-in ASUS SSH server.

### Using a USB drive and Samba in your file manager

If Entware is on a USB drive, **leave the drive connected to the router**.
Open its shared folder on your computer as a network drive and copy the IPK there.

1. In the ASUS web interface, open **USB Application → Servers Center → Network Place (Samba) Share**.
   Menu names vary by firmware. Enable sharing for the required folder on the USB drive
   and give your account read/write access.
2. Connect your computer to the router's home network.
   On Windows, press **Win + E** and enter, for example,
   `\\192.168.1.1\USB` in File Explorer's address bar. This is a network path, without `http://`.
   Enter your Samba account credentials if prompted.
3. Optionally, use **Map network drive** under “This PC” to assign a drive letter.
   You can also work directly in the shared folder.
4. Create a folder named `nfqws2-update` and copy the verified package into it as
   `nfqws2-asus.ipk`, using normal copy and paste.

Other operating systems can open the same network folder:

| OS | How to open it |
| --- | --- |
| Windows | File Explorer: `\\192.168.1.1\USB` |
| Linux | File manager, **Ctrl + L**: `smb://192.168.1.1/USB` |
| macOS | Finder → **Go → Connect to Server**: `smb://192.168.1.1/USB` |

**Your computer's network path differs from the SSH path.** In this example,
the `USB` share exposes the root of a partition mounted on ASUS at `/tmp/mnt/USB`:

| Where you access it | Path to the same file |
| --- | --- |
| Windows File Explorer | `\\192.168.1.1\USB\nfqws2-update\nfqws2-asus.ipk` |
| Router SSH | `/tmp/mnt/USB/nfqws2-update/nfqws2-asus.ipk` |

The share name and mount point may differ from this example.
In SSH, `ls /tmp/mnt` lists mounted drive names;
match the drive with the folder you opened through Samba.

For the example above, copy the package to the prepared Entware directory — **in the router's SSH session**:

```sh
cp "/tmp/mnt/USB/nfqws2-update/nfqws2-asus.ipk" /opt/tmp/nfqws2-asus.ipk
```

First replace `USB` and the folder path if yours differ.
Copying a file through Samba does not start installation.
[Samba setup in ASUS documentation](https://www.asus.com/global/support/faq/1011279/).

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

Open `http://ROUTER_IP:90`.

**ASUS panel login:** use your router administrator username and password.
If the panel cannot read the ASUS system credentials, it automatically enables the
fallback login: **username `root`, password `asus`**.
A separate panel password set earlier is preserved during updates; use that password.
Use **Change password** to set your own panel password.

Follow the ARK check prompts, select devices and a strategy, save the settings,
and start NFQWS2. If you need SmartDNS, connect it using the separate wizard and confirm DNS.

OpenWrt uses a native package: [manual selection and installation](OPENWRT.en.md#choose-a-package-manually).

[Project documentation](README.en.md#documentation).
