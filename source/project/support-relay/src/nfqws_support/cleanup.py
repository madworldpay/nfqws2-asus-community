"""Periodic metadata expiry; no SMTP credentials needed."""
import os
import sys
from .store import RelayStore

if __name__ == '__main__':
    path = '/var/lib/nfqws-support/metadata.sqlite'
    if sys.argv[1:] == ['--entware']:
        from .entware import drop_identity
        drop_identity()
        path = os.path.realpath('/opt/var/lib/nfqws-support/metadata.sqlite')
    elif sys.argv[1:]:
        raise SystemExit(2)
    # The HMAC key is unused by cleanup, which never reserves a submission.
    RelayStore(path, bytes(32)).cleanup()
