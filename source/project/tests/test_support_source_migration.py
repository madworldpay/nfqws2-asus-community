"""Old factory settings migrate without modifying operator files or consent."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
from test_dpi_normalize import PHP, PUBLIC

OLD='https://mad13mans.mooo.com/nfqws-support/v1/reports'
NEW='https://mad13mansprofy13.asuscomm.com:5443/nfqws-support/v1/reports'
class SourceMigrationTests(unittest.TestCase):
    def config(self, value):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'support-relay.json';p.write_text(json.dumps(value));p.chmod(0o600);before=p.read_bytes()
            code="require $argv[1].'/support-mail.php';$m=new AsusSupportMail($argv[2],null,(int)$argv[3]);$f=new ReflectionMethod($m,'config');echo json_encode($f->invoke($m));"
            r=subprocess.run([PHP,'-n','-r',code,str(PUBLIC),str(p),str(os.getuid())],capture_output=True,text=True,check=True)
            self.assertEqual(p.read_bytes(),before)
            return json.loads(r.stdout)
    def test_exact_old_factory_url_migrates_all_enabled_protocols(self):
        out=self.config({'enabled':True,'url':OLD,'dpi_attachments_enabled':True,'sharing_v3_enabled':True,'sharing_v4_enabled':True})
        self.assertEqual(out['url'],NEW)
        self.assertTrue(out['sharing_v4_enabled'])
    def test_custom_urls_new_url_and_disabled_choice_are_preserved(self):
        for url in [NEW,'https://operator.example:8443/nfqws-support/v1/reports',OLD+'?x=1','https://mad13mans.mooo.com:443/nfqws-support/v1/reports']:
            out=self.config({'enabled':True,'url':url})
            if '?' in url:self.assertEqual(out['code'],'invalid_config')
            else:self.assertEqual(out['url'],url)
        self.assertEqual(self.config({'enabled':False,'url':OLD}),{'code':'not_configured'})
