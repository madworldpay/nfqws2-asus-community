import json
from pathlib import Path
import unittest
from test_packages import read_ipk, ROOT
import os
from urllib.parse import urlsplit
import io
import subprocess
import tarfile
import tempfile


class MailPackageTests(unittest.TestCase):
    def test_actual_packages_ship_ready_v4_channel_as_private_preserved_conffile(self):
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
            settings=json.loads(raw)
            self.assertEqual(settings,json.loads((ROOT/'asus/support-relay.json').read_text()))
            self.assertIs(settings['enabled'],True)
            self.assertIs(settings['sharing_v4_enabled'],True)
            self.assertIs(settings['sharing_v3_enabled'],True)
            self.assertIs(settings['dpi_attachments_enabled'],True)
            url=urlsplit(settings['url'])
            self.assertEqual(url.scheme,'https')
            self.assertTrue(url.hostname)
            self.assertEqual(url.path,'/nfqws-support/v1/reports')
            self.assertIsNone(url.username);self.assertIsNone(url.password)
            self.assertEqual(url.query,'');self.assertEqual(url.fragment,'')
            self.assertIn(('/'+config_path+'\n').encode(),control['conffiles'][1])
            for name in ['support-mail.php','support-mail-proof.php','index.php']:
                self.assertEqual(data['opt/share/nfqws-asus-web/'+name][1],(ROOT/'webui/web/public'/name).read_bytes())
            self.assertFalse(any('support-relay/' in name or name.endswith('.py') for name in data))
            versions.append(fields['Version'])
        self.assertEqual(versions[0],versions[1])

    def test_opkg_upgrades_untouched_channel_but_preserves_operator_choices(self):
        opkg=ROOT/'.work/packaging-audit-20261012/opkg-x64'
        self.assertTrue(opkg.is_file(),'real opkg required for conffile upgrade regression')
        new=(ROOT/'asus/support-relay.json').read_bytes()
        self.assertTrue(json.loads(new)['sharing_v4_enabled'])
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            def package(version,raw):
                def section(files):
                    out=io.BytesIO()
                    with tarfile.open(fileobj=out,mode='w:gz') as t:
                        directories={str(parent) for name in files for parent in Path(name).parents if str(parent)!='.'}
                        for name in sorted(directories):
                            info=tarfile.TarInfo(name);info.type=tarfile.DIRTYPE;info.mode=0o755;t.addfile(info)
                        for name,body in files.items():
                            info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o600;t.addfile(info,io.BytesIO(body))
                    return out.getvalue()
                controls={'control':f'Package: nfqws-relay-conffile-test\nVersion: {version}\nArchitecture: all\nDescription: conffile regression\n'.encode(),
                          'conffiles':b'/opt/etc/nfqws-asus-web/support-relay.json\n'}
                parts={'debian-binary':b'2.0\n','control.tar.gz':section(controls),
                       'data.tar.gz':section({'opt/etc/nfqws-asus-web/support-relay.json':raw})}
                p=work/f'config-{version}.ipk'
                with tarfile.open(p,mode='w:gz') as t:
                    for name,body in parts.items():
                        info=tarfile.TarInfo(name);info.size=len(body);info.mode=0o644;t.addfile(info,io.BytesIO(body))
                return p
            old=b'{"enabled":false,"url":""}\n'
            first=package('1',old);second=package('2',new)
            custom={'enabled':False,'url':'https://operator.example/nfqws-support/v1/reports','sharing_v4_enabled':False}
            custom_enabled={**custom,'enabled':True,'sharing_v3_enabled':True}
            for i,edited in enumerate([None,custom,custom_enabled]):
                with self.subTest(operator_modified=edited is not None,enabled=None if edited is None else edited['enabled']):
                    root=work/f'root-{i}';(root/'opt/tmp').mkdir(parents=True);tmp=work/f'tmp-{i}';tmp.mkdir()
                    conf=work/f'opkg-{i}.conf';conf.write_text('dest root /\narch all 100\n')
                    args=[str(opkg),'-f',str(conf),'-o',str(root),'--tmp-dir',str(tmp),'install']
                    p=subprocess.run(args+[str(first)],capture_output=True,text=True,timeout=10)
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                    active=root/'opt/etc/nfqws-asus-web/support-relay.json'
                    if edited is not None:active.write_text(json.dumps(edited))
                    expected=active.read_bytes() if edited is not None else new
                    p=subprocess.run(args+[str(second)],capture_output=True,text=True,timeout=10)
                    self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                    self.assertEqual(active.read_bytes(),expected)
