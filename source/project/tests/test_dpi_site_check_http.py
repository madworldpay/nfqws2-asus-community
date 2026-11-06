"""The service-check route retains panel auth, CSRF and update exclusion."""
import test_support_mail_api as mail


class DpiSiteCheckHttpTests(mail.SupportMailApiTests):
    def setUp(self):
        super().setUp()
        # Substitute only the network producer. The real index/session/lease
        # boundaries run in separate PHP requests, without Internet traffic.
        (self.base / 'dpi-site-check.php').write_text('''<?php
        final class AsusDpiSiteCheck {
          static function validate(array $p):void {
            $keys=array_keys($p);sort($keys);
            if($keys!==['cmd','csrf_token','target']||!is_string($p['csrf_token'])||$p['target']!=='facebook-main')throw new RuntimeException('invalid_request');
          }
          function check(string $target):array {
            file_put_contents(__DIR__.'/site-called',session_status());
            return ['target'=>$target,'http_status'=>400,'full_service_verified'=>false];
          }
        }''')

    def post(self, token):
        return {'cmd': 'dpisitecheck', 'csrf_token': token,
                'target': 'facebook-main'}

    def test_site_route_auth_csrf_origin_and_fields_before_network(self):
        self.assertEqual(self.request(self.post('bad'))[0], 401)
        token = self.login()
        self.assertEqual(self.request(self.post('bad'))[0], 403)
        self.origin = 'http://evil.invalid'
        self.assertEqual(self.request(self.post(token))[0], 403)
        self.origin = 'http://localhost'
        for extra in [{'url': 'https://127.0.0.1/'}, {'target': []},
                      {'csrf_token': []}]:
            self.assertEqual(self.request(self.post(token) | extra)[0], 400)
        self.assertFalse((self.base / 'site-called').exists())

    def test_update_busy_excludes_network_probe(self):
        token = self.login()
        (self.base / 'update-busy').touch()
        self.assertEqual(self.request(self.post(token)),
                         (409, {'error': 'busy'}))
        self.assertFalse((self.base / 'site-called').exists())

    def test_anonymous_session_keeps_own_csrf_and_releases_session(self):
        token = self.login()
        self.change('', token)
        token = self.request({'cmd': 'login'}, 'visitor')[1]['csrf_token']
        self.assertEqual(self.request(self.post(token), 'other')[0], 403)
        code, result = self.request(self.post(token), 'visitor')
        self.assertEqual((code, result), (200, {
            'target': 'facebook-main', 'http_status': 400,
            'full_service_verified': False,
        }))
        # PHP_SESSION_NONE=1: a bounded network request never holds the
        # browser's session lock while waiting on the remote website.
        self.assertEqual((self.base / 'site-called').read_text(), '1')
