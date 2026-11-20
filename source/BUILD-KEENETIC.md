# Build 101 · Keenetic and Netcraze

This archive contains the complete community panel project with the KeeneticOS port.
The published Build 101 source distribution includes the unchanged third-party sources, recipes and notices.
Public base commit: 344c3e92e917a70a89297fccf3c74d375b3a702d.

Prepare Python 3, a Node.js version supported by Vite 7, and the pinned Yarn from this project.
From the root of this archive, create an empty directory named `vendor` and put the four original IPKs listed below in it.
Verify the downloads against `upstream-sha256.txt` from inside that directory.

```sh
cd project/webui/web
node .yarn/releases/yarn-4.12.0.cjs install --immutable
node .yarn/releases/yarn-4.12.0.cjs vite build --base=/nfqws-community/
cd ../..
python3 -B keenetic/build.py --cache ../vendor --dist webui/web/dist --output ../packages
```

## Original IPKs

- [nfqws-keenetic-web_3.0.24_all_entware.ipk](https://github.com/nfqws/nfqws-keenetic-web/releases/download/v3.0.24/nfqws-keenetic-web_3.0.24_all_entware.ipk)
- [nfqws2-keenetic_1.3.3_aarch64-3.10.ipk](https://github.com/nfqws/nfqws2-keenetic/releases/download/v1.3.3/nfqws2-keenetic_1.3.3_aarch64-3.10.ipk)
- [nfqws2-keenetic_1.3.3_mips-3.4.ipk](https://github.com/nfqws/nfqws2-keenetic/releases/download/v1.3.3/nfqws2-keenetic_1.3.3_mips-3.4.ipk)
- [nfqws2-keenetic_1.3.3_mipsel-3.4.ipk](https://github.com/nfqws/nfqws2-keenetic/releases/download/v1.3.3/nfqws2-keenetic_1.3.3_mipsel-3.4.ipk)

[Third-party source distribution for the published Build 101](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build101/nfqws2-asus_1.3.2-asus6%2Bb101_source.tar.gz)
