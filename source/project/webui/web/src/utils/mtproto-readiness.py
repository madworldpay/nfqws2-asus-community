import hashlib, json, os, socket, struct, sys, time
root = os.environ.get('NFQWS_MT_PROBE_ROOT')
if root:
    sys.path[:0] = [root + '/app', root + '/app/vendor']
from proxy._aes import Cipher, algorithms, modes
host, port = sys.argv[1], int(sys.argv[2])
budget = float(sys.argv[3])
if not 0.1 <= budget <= 30:
    raise SystemExit('Invalid readiness deadline')
deadline = time.monotonic() + budget
s = None
try:
    secret = bytes.fromhex(os.environ.get('PROXY_SECRET') or os.environ['NFQWS_MT_PROBE_SECRET'])
    if len(secret) != 16:
        raise ValueError('Invalid proxy key')
    while True:
        h = bytearray(os.urandom(64))
        if h[0] not in (0xef, 0x16) and bytes(h[:4]) not in (b'HEAD', b'POST', b'GET ', b'\xee' * 4, b'\xdd' * 4) and h[4:8] != b'\x00' * 4:
            break
    h[56:60] = b'\xdd' * 4
    h[60:62] = struct.pack('<h', 2)
    k = bytes(h[8:56])
    rev = k[::-1]
    enc = Cipher(algorithms.AES(hashlib.sha256(k[:32] + secret).digest()), modes.CTR(k[32:])).encryptor()
    dec = Cipher(algorithms.AES(hashlib.sha256(rev[:32] + secret).digest()), modes.CTR(rev[32:])).encryptor()
    encrypted = enc.update(bytes(h))
    nonce = os.urandom(16)
    body = struct.pack('<I', 0xbe7e8ef1) + nonce
    message = b'\x00' * 8 + struct.pack('<QI', int(time.time() * (1 << 32)) & ~3, len(body)) + body
    payload = message + os.urandom(12)
    s = socket.create_connection((host, port), timeout=min(3, budget))
    s.settimeout(max(0.01, deadline - time.monotonic()))
    s.sendall(bytes(h[:56]) + encrypted[56:] + enc.update(struct.pack('<I', len(payload)) + payload))
    def receive(size):
        data = b''
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Telegram readiness deadline')
            s.settimeout(remaining)
            part = s.recv(size - len(data))
            if not part:
                raise EOFError('Telegram response missing')
            data += part
        return data
    length = struct.unpack('<I', dec.update(receive(4)))[0]
    if not 56 <= length <= 8192:
        raise ValueError('Invalid Telegram frame')
    data = dec.update(receive(length))
    size = struct.unpack('<I', data[16:20])[0]
    response = data[20:20 + size]
    if data[:8] != b'\x00' * 8 or size < 36 or size > len(data) - 20:
        raise ValueError('Invalid Telegram envelope')
    if response[:4] != b'\x63\x24\x16\x05' or response[4:20] != nonce:
        raise ValueError('Telegram resPQ nonce mismatch')
    print('Telegram resPQ verified (DC2)')
except Exception as error:
    print('Telegram readiness failed: ' + type(error).__name__, file=sys.stderr)
    raise SystemExit(1)
finally:
    if s:
        s.close()
