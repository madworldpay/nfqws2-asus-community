import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'support-relay/src'))
from nfqws_support.app import create_app
from nfqws_support.store import RelayStore
from nfqws_support.smtp import SendOutcome
from test_support_relay_smtp import config
from test_support_relay_validation import fixture, FILENAME


class Sender:
    def __init__(self): self.calls = []; self.state = 'accepted'
    def send(self, raw, filename, info):
        self.calls.append((raw, filename))
        return SendOutcome(self.state)


class HttpTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.sender = Sender()
        self.app = create_app(config(), RelayStore(Path(tmp.name)/'db', b'x'*32), self.sender)
        self.raw = fixture(); self.sid = str(uuid.uuid4())

    def request(self, raw=None, **changes):
        raw = self.raw if raw is None else raw
        env = {'REQUEST_METHOD':'POST', 'PATH_INFO':'/nfqws-support/v1/reports',
               'CONTENT_TYPE':'application/json', 'CONTENT_LENGTH':str(len(raw)),
               'REMOTE_ADDR':'127.0.0.1', 'HTTP_X_REAL_IP':'192.0.2.4',
               'HTTP_X_NFQWS2_SUBMISSION_ID':self.sid, 'HTTP_X_NFQWS2_FILENAME':FILENAME,
               'wsgi.input':io.BytesIO(raw)}
        env.update(changes); response = []
        body = b''.join(self.app(env, lambda s,h: response.append((s,h))))
        self.assertNotIn(b'PRIVATE_CANARY', body)
        self.assertNotIn(b'example.invalid', body)
        return int(response[0][0].split()[0]), json.loads(body)

    def test_valid_request_sends_exact_bytes_once_and_health_never_sends(self):
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.sender.calls, [(self.raw,FILENAME)])
        code, body = self.request(REQUEST_METHOD='GET', PATH_INFO='/health')
        self.assertEqual((code,body), (200,{'state':'ready'}))
        self.assertEqual(len(self.sender.calls), 1)

    def test_closed_input_and_untrusted_proxy_never_send(self):
        for changes in ({'CONTENT_ENCODING':'gzip'}, {'HTTP_CONTENT_ENCODING':'gzip'},
                        {'HTTP_TRANSFER_ENCODING':'chunked'}, {'CONTENT_LENGTH':'1048577'},
                        {'CONTENT_LENGTH':''}, {'CONTENT_TYPE':'text/plain'},
                        {'REMOTE_ADDR':'192.0.2.55'}, {'HTTP_X_REAL_IP':'not-an-ip'},
                        {'HTTP_X_NFQWS2_SUBMISSION_ID':'PRIVATE_CANARY'},
                        {'HTTP_X_NFQWS2_FILENAME':FILENAME+'\r\nPRIVATE_CANARY'}):
            with self.subTest(changes=changes): self.assertEqual(self.request(**changes)[0], 422)
        self.assertEqual(self.request(b'{"PRIVATE_CANARY":1}')[0], 422)
        self.assertEqual(self.sender.calls, [])

    def test_negative_or_uncertain_delivery_is_not_success_and_id_conflicts(self):
        self.sender.state = 'unknown'
        self.assertEqual(self.request()[0], 503)
        self.assertEqual(self.request()[1]['state'], 'unknown')
        self.assertEqual(len(self.sender.calls), 1)
        modified = self.raw.replace(b'"complete": false', b'"complete": true')
        code, value = self.request(modified)
        self.assertEqual((code,value['state'],value['code']), (409,'invalid','id_conflict'))

    def test_spoofed_forwarded_for_cannot_escape_source_quota(self):
        self.sender.state = 'failed_safe'
        for n in range(3):
            raw = self.raw.replace(b'"duration_ms": 10000', ('"duration_ms": '+str(n)).encode())
            self.assertEqual(self.request(raw, HTTP_X_NFQWS2_SUBMISSION_ID=str(uuid.uuid4()), HTTP_X_FORWARDED_FOR=f'198.51.100.{n}')[0], 503)
        self.assertEqual(self.request(HTTP_X_NFQWS2_SUBMISSION_ID=str(uuid.uuid4()))[0], 429)
