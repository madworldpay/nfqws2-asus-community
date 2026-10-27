"""The Entware front proxy cannot let client headers choose quota identity."""
import importlib.util, pathlib, sys, unittest
from test_dpi_normalize import ROOT

class EntwareProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0,str(ROOT/'support-relay/src'))
        try:
            from nfqws_support.entware import trusted_lighttpd
        except ModuleNotFoundError:
            cls.guard=None
        else: cls.guard=staticmethod(trusted_lighttpd)

    def invoke(self,**headers):
        self.assertIsNotNone(self.guard,'Entware proxy boundary is missing')
        seen=[];status=[]
        def app(env,start):seen.append(env);start('200 OK',[]);return [b'ok']
        env={'REMOTE_ADDR':'127.0.0.1','HTTP_X_FORWARDED_FOR':'203.0.113.9','HTTP_X_REAL_IP':'198.51.100.77',**headers}
        body=b''.join(self.guard(app)(env,lambda s,h:status.append(s)))
        return status[0],seen,body

    def test_inbound_real_ip_is_overwritten_with_proxy_appended_address(self):
        status,seen,_=self.invoke(HTTP_X_FORWARDED_FOR='198.51.100.123, 203.0.113.9')
        self.assertEqual(status,'200 OK');self.assertEqual(seen[0]['HTTP_X_REAL_IP'],'203.0.113.9')

    def test_missing_or_invalid_proxy_source_never_reaches_receiver(self):
        for headers in [{'REMOTE_ADDR':'198.51.100.1'},{'HTTP_X_FORWARDED_FOR':''},{'HTTP_X_FORWARDED_FOR':'203.0.113.9,not-an-ip'},{'HTTP_X_FORWARDED_FOR':', '.join(['203.0.113.9']*33)}]:
            with self.subTest(headers=headers):
                status,seen,body=self.invoke(**headers)
                self.assertEqual(status,'400 Bad Request');self.assertEqual(seen,[])

    def test_ipv6_source_accepted_and_input_mapping_not_mutated(self):
        status,seen,_=self.invoke(HTTP_X_FORWARDED_FOR='2001:db8::1')
        self.assertEqual(status,'200 OK');self.assertEqual(seen[0]['HTTP_X_REAL_IP'],'2001:db8::1')

class EntwareRetentionTests(unittest.TestCase):
    def setUp(self):
        import tempfile, time, sqlite3
        from nfqws_support.store import RelayStore
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=RelayStore(pathlib.Path(self.tmp.name)/'metadata.sqlite',b'x'*32)
        now=int(time.time())
        from contextlib import closing
        with closing(sqlite3.connect(self.store.path)) as db:
            for sid,created in [('expired',now-8*86400),('recent',now)]:
                db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?)',(sid,'a'*64,'b'*64,created,created,'accepted'))
            db.commit()
    def ids(self):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.store.path)) as db:return [x[0] for x in db.execute('SELECT id FROM submissions ORDER BY id')]
    def test_startup_expires_metadata_without_any_submission(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from nfqws_support.entware import load_app
        config=SimpleNamespace(hmac_key=b'x'*32,source_limit=3,global_limit=20)
        with patch('nfqws_support.entware.drop_identity'),patch('nfqws_support.config.load_credentials',return_value=config),patch('nfqws_support.store.RelayStore',return_value=self.store):
            load_app()
        self.assertEqual(self.ids(),['recent'])
    def test_idle_cleanup_targets_entware_and_drops_privileges(self):
        import runpy
        from unittest.mock import patch
        with patch.object(sys,'argv',['cleanup','--entware']),patch('nfqws_support.entware.drop_identity') as drop,patch('nfqws_support.store.RelayStore',return_value=self.store) as factory:
            runpy.run_module('nfqws_support.cleanup',run_name='__main__')
            drop.assert_called_once()
            self.assertEqual(factory.call_args.args[0],'/opt/var/lib/nfqws-support/metadata.sqlite')
        self.assertEqual(self.ids(),['recent'])
