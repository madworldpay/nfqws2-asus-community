"""Authentication, origin, CSRF and closed input precede every catalog fetch."""
from test_share_router_http import ShareRouterTests


class ProfileCatalogHttpTests(ShareRouterTests):
    def setUp(self):
        super().setUp()
        path=self.base/'profile-catalog-api.php'
        if path.exists():
            source=path.read_text().replace('new AsusProfileCatalogTransport()','new FixtureCatalogSource()')
            source=source.replace('<?php','<?php require_once __DIR__."/fixture-catalog.php";',1)
            path.write_text(source)
            (self.base/'fixture-catalog.php').write_text('''<?php
            class FixtureCatalogSource {
                function build(){return 68;}
                function catalog(){file_put_contents(__DIR__.'/catalog-fetch','called');return ['schema_version'=>1,'revision'=>1,'profiles'=>[]];}
                function document($id,$sha){file_put_contents(__DIR__.'/catalog-fetch',$id);return '{}';}
            }''')

    def test_catalog_fetch_requires_session_origin_csrf_and_exact_fields(self):
        params={'cmd':'importcatalog','csrf_token':'bad'}
        self.assertEqual(self.request(params)[0],401)
        token=self.login()
        self.assertEqual(self.request(params)[0],403)
        params['csrf_token']=token
        self.origin='https://evil.invalid';self.assertEqual(self.request(params)[0],403);self.origin='http://localhost'
        self.assertEqual(self.request(params|{'url':'https://evil.invalid'})[0],400)
        self.assertFalse((self.base/'catalog-fetch').exists())
        code,value=self.request(params)
        self.assertEqual(code,200,value);self.assertEqual(value['profiles'],[]);self.assertEqual(value['build'],68)
        self.assertTrue((self.base/'catalog-fetch').exists())

    def test_catalog_file_load_rejects_paths_and_bad_hash_before_fetch(self):
        token=self.login();params={'cmd':'importcatalogload','csrf_token':token,'id':'example','sha256':'a'*64}
        for override in [{'id':'../../etc/passwd'},{'sha256':'bad'},{'path':'/etc/passwd'},{'id':['example']}]:
            self.assertEqual(self.request(params|override)[0],400)
        self.assertFalse((self.base/'catalog-fetch').exists())
        code,value=self.request(params)
        self.assertEqual((code,value),(200,{'document':'{}'}))

