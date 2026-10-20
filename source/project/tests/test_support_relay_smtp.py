from email import policy
from email.parser import BytesParser
from pathlib import Path
import smtplib
import ctypes
import json
import os
import socket
import select
import signal
import zlib
from unittest.mock import patch
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'support-relay/src'))
from nfqws_support.config import RelayConfig
from nfqws_support.smtp import SmtpSender
from test_support_relay_validation import fixture, FILENAME
from nfqws_support.validation import validate_report


def config(**extra):
    return RelayConfig(username='sender@example.invalid', password='PRIVATE_CANARY',
                       sender='sender@example.invalid', recipient='support@example.invalid',
                       hmac_key=b'x'*32, **extra)


class FakeSmtp:
    def __init__(self, stage='ok', capture_fd=None):
        self.stage, self.wire, self.closed = stage, None, False
        self.capture_fd=capture_fd

    def ehlo(self): return 250, b'hello'
    def login(self, username, password):
        if self.stage == 'auth': raise smtplib.SMTPAuthenticationError(535, b'PRIVATE_CANARY')
        if self.stage == 'stall': time.sleep(3)
        return 235, b'ok'
    def mail(self, sender): self.sender = sender; return 250, b'ok'
    def rcpt(self, recipient): self.recipient = recipient; return 250, b'ok'
    def docmd(self, command):
        if self.stage == 'before_data': raise smtplib.SMTPServerDisconnected('PRIVATE_CANARY')
        return 354, b'go'
    def send(self, wire):
        self.wire = wire
        if self.stage == 'during_data': raise OSError('PRIVATE_CANARY')
    def getreply(self):
        if self.stage == 'after_data': raise smtplib.SMTPServerDisconnected('PRIVATE_CANARY')
        return (550, b'PRIVATE_CANARY') if self.stage == 'rejected' else (250, b'queued')
    def quit(self):
        if self.stage == 'quit': raise OSError('PRIVATE_CANARY')
    def close(self):
        self.closed = True
        if self.capture_fd is not None:
            record=json.dumps({'wire':self.wire.decode('ascii'),'sender':self.sender,'recipient':self.recipient}).encode()
            os.write(self.capture_fd,zlib.compress(record))



class SmtpTests(unittest.TestCase):
    def test_fixed_envelope_and_exact_decoded_attachment(self):
        raw = fixture(); read_fd,write_fd=os.pipe()
        try:
            fake=FakeSmtp(capture_fd=write_fd)
            sender = SmtpSender(config(), factory=lambda **kw: fake)
            self.assertEqual(sender.send(raw, FILENAME, validate_report(raw, FILENAME)).state, 'accepted')
            os.close(write_fd); write_fd=None
            record=json.loads(zlib.decompress(os.read(read_fd,262144)))
        finally:
            os.close(read_fd)
            if write_fd is not None: os.close(write_fd)
        wire=record['wire'].encode('ascii')
        msg = BytesParser(policy=policy.default).parsebytes(wire[:-3])
        attachment, = msg.iter_attachments()
        self.assertEqual(attachment.get_payload(decode=True), raw)
        self.assertEqual(attachment.get_filename(), FILENAME)
        self.assertEqual(record['sender'], 'sender@example.invalid')
        self.assertEqual(record['recipient'], 'support@example.invalid')
        self.assertEqual(str(msg['Subject']), 'NFQWS2 diagnostic report')
        self.assertNotIn(b'PRIVATE_CANARY', wire)

    def test_network_stage_determines_safe_or_ambiguous_failure(self):
        raw = fixture(); info = validate_report(raw, FILENAME)
        for stage, expected in [('auth','failed_safe'), ('before_data','failed_safe'),
                                ('during_data','unknown'), ('after_data','unknown'),
                                ('rejected','failed_safe'), ('quit','accepted')]:
            with self.subTest(stage=stage):
                result = SmtpSender(config(), factory=lambda **kw: FakeSmtp(stage)).send(raw, FILENAME, info)
                self.assertEqual(result.state, expected)
                self.assertNotIn('PRIVATE_CANARY', repr(result))

    def test_one_overall_deadline_covers_connect_and_auth_stalls(self):
        raw = fixture(); info = validate_report(raw, FILENAME)
        def blocked(**kw): time.sleep(3)
        for factory in (blocked, lambda **kw: FakeSmtp('stall')):
            start = time.monotonic()
            result = SmtpSender(config(), factory=factory, deadline_seconds=0.15).send(raw, FILENAME, info)
            self.assertEqual(result.state, 'failed_safe')
            self.assertLess(time.monotonic()-start, 0.6)

    def test_native_resolver_stall_obeys_overall_deadline(self):
        raw=fixture(); info=validate_report(raw,FILENAME)
        libc=ctypes.CDLL(None)
        libc.system.argtypes=[ctypes.c_char_p]; libc.system.restype=ctypes.c_int
        def blocked(*args,**kwargs):
            libc.system(b'sleep 0.6')
            raise socket.gaierror('synthetic resolver failure')
        with patch('socket.getaddrinfo',blocked):
            started=time.monotonic()
            result=SmtpSender(config(),deadline_seconds=0.1).send(raw,FILENAME,info)
            elapsed=time.monotonic()-started
        self.assertEqual(result.state,'failed_safe')
        self.assertLess(elapsed,0.3)

    def test_killed_or_stalled_child_preserves_last_confirmed_smtp_phase(self):
        raw=fixture(); info=validate_report(raw,FILENAME)
        class TerminatedSmtp(FakeSmtp):
            def login(self,*args):
                if self.stage=='kill_before': os._exit(1)
                return super().login(*args)
            def send(self,wire):
                if self.stage=='kill_during': os._exit(1)
                if self.stage=='stall_during': time.sleep(3)
                return super().send(wire)
            def quit(self):
                if self.stage=='kill_after': os._exit(1)
                if self.stage=='stall_after': time.sleep(3)
        for stage,expected in [('kill_before','failed_safe'),('kill_during','unknown'),
                               ('stall_during','unknown'),('kill_after','accepted'),('stall_after','accepted')]:
            with self.subTest(stage=stage):
                started=time.monotonic()
                result=SmtpSender(config(),factory=lambda **kw:TerminatedSmtp(stage),deadline_seconds=0.15).send(raw,FILENAME,info)
                self.assertEqual(result.state,expected)
                self.assertLess(time.monotonic()-started,0.6)

    def test_smtp_child_dies_when_request_worker_is_killed(self):
        raw=fixture(); info=validate_report(raw,FILENAME)
        read_fd,write_fd=os.pipe()
        worker=os.fork()
        if worker==0:
            os.close(read_fd)
            class WaitingSmtp(FakeSmtp):
                def login(self,*args):
                    os.write(write_fd,b'ready')
                    time.sleep(2)
                    os.write(write_fd,b'unexpected_survivor')
                    return 235,b'ok'
            SmtpSender(config(),factory=lambda **kw:WaitingSmtp()).send(raw,FILENAME,info)
            os._exit(0)
        os.close(write_fd)
        try:
            self.assertTrue(select.select([read_fd],[],[],2)[0])
            self.assertEqual(os.read(read_fd,5),b'ready')
            os.kill(worker,signal.SIGKILL); os.waitpid(worker,0); worker=None
            self.assertTrue(select.select([read_fd],[],[],1)[0])
            self.assertEqual(os.read(read_fd,64),b'')
        finally:
            os.close(read_fd)
            if worker is not None:
                try: os.kill(worker,signal.SIGKILL)
                except ProcessLookupError: pass
                os.waitpid(worker,0)
