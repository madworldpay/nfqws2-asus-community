import json
from pathlib import Path
import unittest
from test_packages import read_ipk, ROOT
import os


class MailPackageTests(unittest.TestCase):
    def test_actual_packages_declare_https_and_preserve_private_disabled_conffile(self):
        packages=list(Path(os.environ.get('PACKAGES_DIR',ROOT/'dist')).glob('*.ipk'))
        self.assertEqual(len(packages),2)
        versions=[]
        for path in packages:
            package=read_ipk(path);control=package['control'];data=package['data']
            fields=dict(line.split(': ',1) for line in control['control'][1].decode().splitlines() if ': ' in line)
            deps={item.strip() for item in fields['Depends'].split(',')}
            self.assertTrue({'php8-mod-openssl','ca-bundle'} <= deps,'HTTPS must work on a fresh Entware install')
            config_path='opt/etc/nfqws-asus-web/support-relay.json'
            self.assertIn(config_path,list(data))
            info,raw=data[config_path]
            self.assertEqual((info.mode,info.uid,info.gid),(0o600,0,0))
            self.assertEqual(json.loads(raw),{'enabled':False,'url':''})
            self.assertIn(('/'+config_path+'\n').encode(),control['conffiles'][1])
            for name in ['support-mail.php','support-mail-proof.php','index.php']:
                self.assertEqual(data['opt/share/nfqws-asus-web/'+name][1],(ROOT/'webui/web/public'/name).read_bytes())
            self.assertFalse(any('support-relay/' in name or name.endswith('.py') for name in data))
            versions.append(fields['Version'])
        self.assertEqual(versions[0],versions[1])
