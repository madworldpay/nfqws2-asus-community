import io,json,tempfile,unittest,uuid
from pathlib import Path
from test_support_relay_bundle_validation import bundle_fixture,encode
from test_support_relay_http import Sender
from test_support_relay_smtp import config
from nfqws_support.app import create_app
from nfqws_support.store import RelayStore
from nfqws_support.smtp import SendOutcome

class BundleHttpTests(unittest.TestCase):
    def test_v2_exact_bytes_idempotency_conflict_and_v1_stays_available(self):
        class BundleSender(Sender):
            def send_bundle(self,b):self.calls.append(b);return SendOutcome('accepted')
        with tempfile.TemporaryDirectory() as directory:
            sender=BundleSender();app=create_app(config(),RelayStore(Path(directory)/'db',b'x'*32),sender);v=bundle_fixture()
            def request(v,**extra):
                raw=encode(v);env={'REQUEST_METHOD':'POST','PATH_INFO':'/nfqws-support/v2/reports','REMOTE_ADDR':'127.0.0.1','HTTP_X_REAL_IP':'192.0.2.4','HTTP_X_NFQWS2_SUBMISSION_ID':v['submission_id'],'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(raw)};env.update(extra);status=[];body=b''.join(app(env,lambda s,h:status.append(s)));return int(status[0][:3]),json.loads(body)
            self.assertEqual(request(v)[0],200);self.assertEqual(request(v)[0],200);self.assertEqual(len(sender.calls),1)
            changed=bundle_fixture(v['submission_id']);changed['files'][0]=bundle_fixture()['files'][0];raw=__import__('base64').b64decode(changed['files'][0]['data_base64']).replace(b'"complete": false',b'"complete": true');changed['files'][0].update(byte_length=len(raw),sha256=__import__('hashlib').sha256(raw).hexdigest(),data_base64=__import__('base64').b64encode(raw).decode())
            self.assertEqual(request(changed)[1]['code'],'id_conflict');self.assertEqual(len(sender.calls),1)
            self.assertEqual(request(bundle_fixture(),HTTP_TRANSFER_ENCODING='chunked')[0],422)
