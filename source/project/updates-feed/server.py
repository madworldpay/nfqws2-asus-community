"""Authenticated, loopback-only package feed. No upload, proxy or request logging."""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import stat
import threading

from common import MAX_PACKAGE, PACKAGE_RE, VERSION_RE, current_version, decode, directory, read_regular


def load_config(path, owner=None, credential=False):
    owner = os.geteuid() if owner is None else owner
    try:
        info = Path(path).lstat()
        if stat.S_IMODE(info.st_mode) not in ([0o400, 0o440] if credential else [0o400, 0o600]):
            raise ValueError()
        value = decode(read_regular(path, 16384, owner))
        if (not isinstance(value, dict) or set(value) != {'token', 'release_root'}
                or not isinstance(value['token'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', value['token'])
                or not isinstance(value['release_root'], str) or not value['release_root'].startswith('/')):
            raise ValueError()
        return value
    except (OSError, ValueError, TypeError):
        raise ValueError('invalid_config') from None


class FeedServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, release_root, token, owner=0):
        if address[0] != '127.0.0.1' or not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', token):
            raise ValueError('invalid_config')
        self.release_root = Path(release_root)
        self.owner = owner
        directory(self.release_root, owner)
        self._token = token.encode('ascii')
        self._request_slots = threading.BoundedSemaphore(8)
        self._downloads = threading.BoundedSemaphore(2)
        super().__init__(address, FeedHandler)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

    def handle_error(self, request, client_address):
        pass  # Never persist request paths, addresses or credentials.


class FeedHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def respond(self, status, raw=b'', content_type='application/octet-stream'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(raw)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        auth = self.headers.get('Authorization', '')
        if (len(auth) > 256 or not auth.startswith('Bearer ')
                or not hmac.compare_digest(auth[7:].encode('utf-8'), self.server._token)):
            self.respond(403, b'{"error":"forbidden"}', 'application/json')
            return
        prefix = '/nfqws-updates/v1/'
        if not self.path.startswith(prefix):
            self.respond(404)
            return
        route = self.path[len(prefix):]
        slot = False
        try:
            root, owner = self.server.release_root, self.server.owner
            if route == 'manifest.json':
                version = current_version(root, owner)
                path, cap = root/'releases'/version/'manifest.json', 32768
            elif route == 'manifest.sig':
                match = re.fullmatch(r'"([a-f0-9]{64})"', self.headers.get('If-Match', ''))
                if not match:
                    self.respond(412)
                    return
                path = None
                for release in (root/'releases').iterdir():
                    if not VERSION_RE.fullmatch(release.name):
                        continue
                    directory(release, owner)
                    if hmac.compare_digest(hashlib.sha256(read_regular(release/'manifest.json', 32768, owner)).hexdigest(), match[1]):
                        path = release/'manifest.sig'
                        break
                if path is None:
                    self.respond(412)
                    return
                cap = 1024
            elif route.startswith('packages/') and (match := PACKAGE_RE.fullmatch(route[9:])):
                slot = self.server._downloads.acquire(blocking=False)
                if not slot:
                    self.respond(503)
                    return
                path, cap = root/'releases'/match[1]/route[9:], MAX_PACKAGE
            else:
                self.respond(404)
                return
            raw = read_regular(path, cap, owner)
            self.respond(200, raw)
        except (OSError, ValueError, TypeError):
            self.respond(404)
        finally:
            if slot:
                self.server._downloads.release()


if __name__ == '__main__':
    config = load_config(Path(os.environ.get('CREDENTIALS_DIRECTORY', '/run/credentials/nfqws-updates.service'))/'feed-config', owner=0, credential=True)
    FeedServer(('127.0.0.1', 8876), config['release_root'], config['token']).serve_forever()
