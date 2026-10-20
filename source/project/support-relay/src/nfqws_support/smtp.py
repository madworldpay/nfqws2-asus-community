"""Fixed-envelope SMTP, with a single wall-clock budget including DNS."""

from dataclasses import dataclass
from email.message import EmailMessage
from email import policy
import re
import ctypes
import os
import select
import time
import signal
import smtplib
import ssl
import threading
from .share import ShareBundle,share_subject,share_body


@dataclass(frozen=True)
class SendOutcome:
    state: str


# A signal in Python cannot interrupt every native resolver/TLS call. A short-
# lived Linux child owns the entire SMTP operation; the parent enforces the
# wall-clock budget. Only phase bytes cross the pipe, never reports/secrets.
_LIBC = ctypes.CDLL(None, use_errno=True)


def _parent_bound(parent_pid):
    # Kill the SMTP child if its Gunicorn worker disappears, including SIGKILL.
    # Check the race between fork and PR_SET_PDEATHSIG installation as well.
    return (_LIBC.prctl(1, signal.SIGKILL, 0, 0, 0) == 0
            and os.getppid() == parent_pid)


def _connect(*, port, context, timeout):
    if port == 465:
        return smtplib.SMTP_SSL('smtp.gmail.com', port, context=context, timeout=timeout)
    server = smtplib.SMTP('smtp.gmail.com', port, timeout=timeout)
    try:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        return server
    except BaseException:
        server.close()
        raise


class SmtpSender:
    def __init__(self, config, factory=_connect, deadline_seconds=10):
        self.config, self.factory, self.seconds = config, factory, deadline_seconds

    def send_bundle(self, bundle):
        return self.send(None,None,bundle)

    def send(self, raw, filename, info):
        if threading.current_thread() is not threading.main_thread():
            return SendOutcome('failed_safe')
        expires=time.monotonic()+self.seconds
        read_fd,write_fd=os.pipe()
        parent_pid=os.getpid()
        try:
            child=os.fork()
        except OSError:
            os.close(read_fd); os.close(write_fd)
            return SendOutcome('failed_safe')
        if child == 0:
            os.close(read_fd)
            try:
                if _parent_bound(parent_pid):
                    self._send(raw,filename,info,write_fd)
            except BaseException:
                pass  # No exception text, credentials or body reaches logs.
            finally:
                os._exit(0)
        os.close(write_fd)
        state='failed_safe'
        try:
            while True:
                remaining=expires-time.monotonic()
                if remaining<=0: break
                if not select.select([read_fd],[],[],remaining)[0]: break
                phases=os.read(read_fd,64)
                if not phases: break
                for phase in phases:
                    if phase==ord('D'): state='unknown'
                    elif phase==ord('A'): state='accepted'
                    elif phase==ord('S'): state='failed_safe'
                    elif phase==ord('U'): state='unknown'
        finally:
            os.close(read_fd)
            # No SMTP operation survives a request deadline or completed result.
            try: os.kill(child,signal.SIGKILL)
            except ProcessLookupError: pass
            while True:
                try: os.waitpid(child,0); break
                except InterruptedError: continue
        return SendOutcome(state)

    def _send(self, raw, filename, info, phase_fd):
        # The caller has already validated the closed report schema and name.
        msg = EmailMessage(policy=policy.SMTP)
        msg['From'], msg['To'] = self.config.sender, self.config.recipient
        if isinstance(info,ShareBundle):
            msg['Subject']=share_subject(info.files)
            msg['X-NFQWS2-Submission-ID']=info.submission_id
            msg.set_content(share_body(info))
        else:
            msg['Subject'] = 'NFQWS2 diagnostic report'
            msg.set_content('A diagnostic report is attached.\n')
        if raw is None:
            for f in info.files:
                msg.add_attachment(f.raw, maintype='application', subtype='json', filename=f.filename)
        else:
            msg.add_attachment(raw, maintype='application', subtype='json', filename=filename)
        wire = msg.as_bytes()
        wire = re.sub(br'(?m)^\.', b'..', wire)
        if not wire.endswith(b'\r\n'): wire += b'\r\n'
        wire += b'.\r\n'
        server = None
        transmitting = accepted = False
        def emit(value): os.write(phase_fd,value)
        try:
            server = self.factory(port=self.config.port, context=ssl.create_default_context(), timeout=self.seconds)
            server.ehlo()
            server.login(self.config.username, self.config.password)
            code, _ = server.mail(self.config.sender)
            if code != 250: emit(b'S'); return
            code, _ = server.rcpt(self.config.recipient)
            if code not in (250,251): emit(b'S'); return
            code, _ = server.docmd('DATA')
            if code != 354: emit(b'S'); return
            emit(b'D')
            transmitting = True
            server.send(wire)
            code, _ = server.getreply()
            if code != 250: emit(b'S'); return
            accepted = True
            emit(b'A')
            server.quit()
        except Exception:
            emit(b'A' if accepted else (b'U' if transmitting else b'S'))
        finally:
            if server is not None:
                try: server.close()
                except Exception: pass
