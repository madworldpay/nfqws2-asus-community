from email import policy
from email.parser import BytesParser
import json,os,unittest,zlib
from test_support_relay_smtp import config,FakeSmtp
from test_support_relay_bundle_validation import bundle_fixture,encode,validate_bundle
from nfqws_support.smtp import SmtpSender

class BundleSmtpTests(unittest.TestCase):
    def test_two_exact_mime_attachments_and_same_deadline_transport(self):
        v=bundle_fixture();bundle=validate_bundle(encode(v),v['submission_id']);r,w=os.pipe()
        try:
            fake=FakeSmtp(capture_fd=w);self.assertEqual(SmtpSender(config(),factory=lambda **kw:fake).send_bundle(bundle).state,'accepted');os.close(w);w=None
            record=json.loads(zlib.decompress(os.read(r,262144)))
        finally:
            os.close(r)
            if w is not None:os.close(w)
        msg=BytesParser(policy=policy.default).parsebytes(record['wire'].encode()[:-3]);files=list(msg.iter_attachments());self.assertEqual(len(files),2)
        for part,f in zip(files,bundle.files):self.assertEqual(part.get_filename(),f.filename);self.assertEqual(part.get_payload(decode=True),f.raw)
        self.assertEqual(str(msg['Subject']),'NFQWS2 diagnostic report');self.assertNotIn('PRIVATE_CANARY',record['wire'])
