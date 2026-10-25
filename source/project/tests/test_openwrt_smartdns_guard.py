"""Run the generated native validation guardian's real session cleanup cases."""
import tempfile
from pathlib import Path
import test_smartdns_config_guard as guards
from test_openwrt_builder import builder
class NativeSmartDnsValidationGuard(guards.ConfigGuardTests):
    def setup_fixture(self,directory,mode):
        source=builder.smartdns_runtime_files()['usr/lib/nfqws2/smartdns/config-worker.sh'][0].decode()
        # Reuse confined fixture plumbing; keep the native setsid/sleep algorithm.
        for native,legacy in [('/etc/nfqws2-web/smartdns','/opt/etc/nfqws-asus-web/smartdns'),('/usr/lib/nfqws2/smartdns','/opt/lib/nfqws2-asus/smartdns'),('/tmp/nfqws2-native-state/updates','/opt/var/lib/nfqws2-asus/updates'),('/usr/bin/php-cgi','/opt/bin/php-cgi')]:source=source.replace(native,legacy)
        path=Path(directory)/'native-config-worker.sh';path.write_text(source)
        old=guards.SCRIPT
        try:
            guards.SCRIPT=path
            return super().setup_fixture(directory,mode)
        finally:guards.SCRIPT=old
