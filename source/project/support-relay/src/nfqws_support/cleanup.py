"""Hourly metadata expiry; no SMTP credentials needed."""
from .store import RelayStore

if __name__ == '__main__':
    # The HMAC key is unused by cleanup, which never reserves a submission.
    RelayStore('/var/lib/nfqws-support/metadata.sqlite', bytes(32)).cleanup()
