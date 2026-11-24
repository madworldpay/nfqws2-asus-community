"""Exercise the common installer at its normal entry with isolated firmware and opkg."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import unittest

import test_install


CORE = "nfqws2-keenetic"
WEB = "nfqws-keenetic-web"
PANEL = "nfqws2-keenetic-community"
VERSION = "1.3.3+b106-2"
ABI = {"mipsel-3.4": "mips", "mips-3.4": "mips", "aarch64-3.10": "aarch64"}
ENTRY = "opt/share/www/nfqws/nfqws-community/index.php"
OPKG = r"""
import subprocess
args = sys.argv[1:]
if args[:1] == ["--tmp-dir"]:
    assert pathlib.Path(args[1]).is_dir()
    args = args[2:]
action = args[0]
if action == "print-architecture":
    print(state["arches"], end="")
elif action == "status":
    name = args[1]
    if name in state["packages"]:
        print("Package:", name)
        print("Version:", state["packages"][name])
        print("Status:", state.get("status", "install user installed"))
elif action == "compare-versions":
    sys.exit(subprocess.run(["dpkg", "--compare-versions", *args[1:]]).returncode)
elif action == "update":
    emit({"kind":"update"})
elif action == "--noaction" or action == "install":
    import tarfile
    if action == "--noaction":
        assert args[1] == "install"
        files = args[2:]
    else:
        files = args[1:]
    assert files and all(pathlib.Path(f).is_file() for f in files)
    if action == "--noaction":
        for file in map(pathlib.Path, files):
            if file.parent.name != "stock":
                continue
            def contents(path, prepared):
                with tarfile.open(path) as pkg:
                    control = pkg.extractfile("control.tar.gz").read()
                    version = pkg.extractfile("debian-binary").read()
                    with tarfile.open(fileobj=pkg.extractfile("data.tar.gz")) as payload:
                        result = {}
                        for m in payload:
                            key = m.name.removeprefix("./")
                            if prepared:
                                assert (m.uid, m.gid) == (0, 0), m
                            if m.isfile():
                                result[key] = (m.mode, m.mtime, payload.extractfile(m).read())
                            elif prepared:
                                assert not (work/"router"/key).is_dir(), key
                return control, version, result
            assert contents(work/"http"/file.name, False) == contents(file, True)
    emit({"kind": action, "files": [pathlib.Path(f).name for f in files]})
    if action == "install":
        if state["install_error"]:
            sys.exit(1)
        for file in files:
            name, version, arch = pathlib.Path(file).name.split("_", 2)
            state["packages"][name] = version
        state_path.write_text(json.dumps(state))
        entry = work/"router"/"opt/share/www/nfqws/nfqws-community/index.php"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.touch()
else:
    raise AssertionError(args)
"""


class KeeneticInstallTests(unittest.TestCase):
    def setUp(self):
        f = self.fixture = test_install.InstallerTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.state.update(model="KN-1711", packages={})
        self.set_abi("mipsel-3.4")
        f.tool("ndmc", 'assert sys.argv[1:] == ["-c", "show version"]; print(" hw_id:", state["model"])')
        body = test_install.INSTALLER.read_text()
        # Redirect hardware probes, as in the ASUS tests. Preserve the real dispatcher.
        body = body.replace("/bin/ndmc", str(f.bin/"ndmc"))
        body = body.replace("/etc/openwrt_release", str(f.router/"openwrt_release"))
        body = body.replace("$(id -u)", "0")
        f.tool("opkg", OPKG, f.router/"opt/bin/opkg")
        f.tool("curl", r'''
import shutil
args = sys.argv[1:]
url = args[-1]
assert url.startswith(("https://github.com/nfqws/", "https://github.com/madworldpay/"))
assert args[args.index("--proto")+1] == "=https"
assert args[args.index("--proto-redir")+1] == "=https"
name = url.rsplit("/", 1)[1]
emit({"kind":"download","file":name})
shutil.copyfile(work/"http"/name, args[args.index("-o")+1])
''')
        # For offline developer tests only the release hashes change. The optional
        # published IPK fixture exercises exactly the embedded production hashes.
        upstream = os.environ.get("NFQWS_TEST_KEENETIC_RELEASE")
        web = WEB+"_3.0.24_all_entware.ipk"
        if upstream:
            release = Path(upstream)
            for path in [*(release/"inputs/vendor").glob("*.ipk"), *(release/"keenetic-packages").glob("*.ipk")]:
                os.symlink(path, f.http/path.name)
            for abi in ABI:
                assert all((f.http/name).is_file() for name in self.names(abi))
        else:
            start = body.index("nfqws_keenetic_main() {")
            header, tail = body[:start], body[start:]
            for abi in ABI:
                core, _, panel = self.names(abi)
                begin = tail.index("core_sha=", tail.index("        "+abi+":"))
                end = tail.index(" ;;", begin)
                tail = tail[:begin]+"core_sha="+self.asset(core)+"\n            panel_sha="+self.asset(panel)+tail[end:]
            marker = 'keenetic_stock_asset "$file" '
            begin = tail.index(marker, tail.index('file="${web}_3.0.24_all_entware.ipk"'))+len(marker)
            end = tail.index(" ", begin)
            tail = tail[:begin]+self.asset(web)+tail[end:]
            body = header+tail
        f.installer = f.work/"common-entry.sh"
        f.installer.write_text(body)

    def asset(self, name):
        def archive(entries):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as stream:
                for path, data in entries:
                    member = tarfile.TarInfo(path)
                    member.uid = member.gid = 1001
                    member.mtime = 1720000000
                    if data is None:
                        member.type = tarfile.DIRTYPE
                        member.mode = 0o755
                        stream.addfile(member)
                    else:
                        member.size = len(data)
                        stream.addfile(member, io.BytesIO(data))
            return buffer.getvalue()

        payload = archive([(".", None), ("./opt", None), ("./opt/etc", None),
                           ("./opt/etc/stock", None), ("./opt/etc/stock/fixture", name.encode())])
        data = archive([("debian-binary", b"2.0\n"), ("control.tar.gz", b"fixture-control"),
                        ("data.tar.gz", payload)])
        (self.fixture.http/name).write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def names(self, abi):
        return [f"{CORE}_1.3.3_{abi}.ipk", WEB+"_3.0.24_all_entware.ipk", f"{PANEL}_{VERSION}_{abi}.ipk"]

    def set_abi(self, abi):
        self.fixture.state.update(cpu=ABI[abi], arches=f"arch all 100\narch {abi} 150\n")

    def test_package_selection_on_all_three_architectures_is_read_only(self):
        f = self.fixture
        (f.router/"openwrt_release").touch()
        for abi in ABI:
            with self.subTest(abi=abi):
                self.set_abi(abi)
                f.state["model"] = "NC-1812" if abi == "aarch64-3.10" else "KN-1711"
                f.log.unlink(missing_ok=True)
                r = f.execute("--check")
                self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
                self.assertIn(f.state["model"], r.stdout)
                self.assertEqual([v["file"] for v in f.events], self.names(abi))

    def test_clean_install_uses_usb_asset_then_repeated_install_is_a_noop(self):
        f = self.fixture
        names = self.names("mipsel-3.4")
        usb = f.router/"opt/packages"
        usb.mkdir()
        shutil.copyfile(f.http/names[-1], usb/names[-1])
        r = f.execute()
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertEqual([v["file"] for v in f.events if v["kind"] == "download"], names[:2])
        self.assertEqual([v["files"] for v in f.events if v["kind"] in ("--noaction", "install")], [names, names])
        f.state = json.loads(f.state_path.read_text())
        f.log.unlink()
        r = f.execute()
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertIn("уже установлен", r.stdout)
        self.assertFalse(f.events)

    def test_keeneticos_prefers_vendor_feed_but_accepts_the_registered_base_abi(self):
        f = self.fixture
        for abi in ABI:
            self.set_abi(abi)
            f.state["model"] = "NC-1812" if abi == "aarch64-3.10" else "KN-1711"
            for priority in (200, 150):
                with self.subTest(abi=abi, priority=priority):
                    f.state["arches"] = f"arch all 100\narch {abi} 150\narch {abi}_kn {priority}\n"
                    f.log.unlink(missing_ok=True)
                    result = f.execute("--check")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual([row["file"] for row in f.events], self.names(abi))

    def test_vendor_feed_needs_its_base_abi_to_accept_an_ipk(self):
        f = self.fixture
        for arches in (
            "arch mipsel-3.4_kn 200\n",
            "arch mipsel-3.4 0\narch mipsel-3.4_kn 200\n",
            "arch mipsel-3.4 150\narch mips-3.4_kn 200\n",
            "arch mipsel-3.4 150\narch mipsel-3.4_kn 200\narch unsupported 200\n",
        ):
            with self.subTest(arches=arches):
                f.state["arches"] = "arch all 100\n" + arches
                result = f.execute("--check")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(f.events)

    def test_existing_stock_packages_and_newer_web_are_retained(self):
        f = self.fixture
        f.state["packages"] = {CORE:"1.3.3", WEB:"3.0.25"}
        r = f.execute()
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assertEqual([v["files"] for v in f.events if v["kind"] == "install"], [[self.names("mipsel-3.4")[-1]]])

    def test_newer_conflicting_broken_or_ambiguous_targets_stop_before_download(self):
        f = self.fixture
        for changes in [
            {"packages": {CORE: "1.3.4"}},
            {"packages": {PANEL: "1.3.3+b106-3"}},
            {"packages": {"nfqws2-asus": "1"}},
            {"packages": {PANEL: VERSION}, "status": "install user unpacked"},
            {"arches": "arch mipsel-3.4 110\narch mips-3.4 110\n"},
            {"model": "unidentified"},
        ]:
            with self.subTest(changes=changes):
                original = f.state.copy()
                f.state.update(changes)
                r = f.execute()
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(f.events)
                f.state = original

    def test_changed_package_bytes_never_reach_opkg(self):
        f = self.fixture
        name = self.names("mipsel-3.4")[-1]
        path = f.http/name
        path.unlink()
        path.write_bytes(b"wrong")
        r = f.execute()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Контрольная сумма", r.stderr)
        self.assertTrue(all(v["kind"] == "download" for v in f.events))

    def test_stock_repack_failure_preserves_installed_packages(self):
        f = self.fixture
        f.tool("tar", 'args=sys.argv[1:]\nif "-tzf" in args: sys.exit(1)\nos.execv("/usr/bin/tar", ["tar", *args])')
        r = f.execute()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("подготовить штатный пакет", r.stderr)
        self.assertFalse(any(v["kind"] in ("--noaction", "install") for v in f.events))

    def test_failed_native_transaction_reports_failure(self):
        f = self.fixture
        f.state["install_error"] = True
        r = f.execute()
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Готово", r.stdout)
        self.assertFalse((f.router/ENTRY).exists())


if __name__ == "__main__":
    unittest.main()
