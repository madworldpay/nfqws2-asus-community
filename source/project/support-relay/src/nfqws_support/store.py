"""Short, atomic quota reservations. Report bodies and raw IPs never enter SQL."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
from pathlib import Path
import re
import sqlite3
import time
import uuid


@dataclass(frozen=True)
class Reservation:
    decision: str
    submission_id: str
    retry_after: int = 0


def valid_submission_id(value):
    try:
        parsed = uuid.UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except (ValueError, TypeError, AttributeError):
        return False


class RelayStore:
    def __init__(self, db_path, hmac_key, clock=time.time, source_limit=3, global_limit=20):
        if not isinstance(hmac_key, bytes) or len(hmac_key) < 32:
            raise ValueError('invalid_config')
        self.path = Path(db_path)
        self.key, self.clock = hmac_key, clock
        self.source_limit, self.global_limit = source_limit, global_limit
        with self._connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL, source TEXT NOT NULL,
                created INTEGER NOT NULL, lease INTEGER NOT NULL, state TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS by_digest ON submissions(digest)')
            db.execute('CREATE INDEX IF NOT EXISTS by_created ON submissions(created)')

    @contextmanager
    def _connect(self):
        # umask from the unit is 0077; SQLite sidecars inherit the database mode.
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        self.path.chmod(0o600)
        try:
            db.execute('PRAGMA secure_delete=ON')
            yield db
        finally:
            db.close()

    @staticmethod
    def _expire(db, now):
        db.execute("UPDATE submissions SET state='unknown' WHERE state='sending' AND lease<=?", (now,))
        # Hourly cleanup gets one interval of margin below the seven-day cap.
        db.execute('DELETE FROM submissions WHERE created<?', (now-(7*86400-3600),))

    def reserve(self, submission_id, digest, remote_addr):
        if not valid_submission_id(submission_id) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('invalid_request')
        address = str(ipaddress.ip_address(remote_addr))
        now = int(self.clock())
        day = now // 86400 * 86400
        source = hmac.new(self.key, f'{day}\0{address}'.encode('ascii'), hashlib.sha256).hexdigest()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                self._expire(db, now)
                previous = db.execute('SELECT digest,state FROM submissions WHERE id=?', (submission_id,)).fetchone()
                if previous:
                    decision = 'id_conflict' if previous[0] != digest else ('busy' if previous[1] == 'sending' else previous[1])
                    result = Reservation(decision, submission_id, 30 if decision == 'busy' else 0)
                else:
                    existing = db.execute("SELECT state FROM submissions WHERE digest=? AND state IN ('sending','accepted','unknown') ORDER BY created LIMIT 1", (digest,)).fetchone()
                    active = db.execute("SELECT 1 FROM submissions WHERE state='sending' LIMIT 1").fetchone()
                    counts = db.execute('SELECT count(*),coalesce(sum(source=?),0) FROM submissions WHERE created>=?', (source,day)).fetchone()
                    if existing:
                        decision = 'busy' if existing[0] == 'sending' else existing[0]
                        result = Reservation(decision, submission_id, 30 if decision == 'busy' else 0)
                    elif active:
                        result = Reservation('busy', submission_id, 30)
                    elif counts[0] >= self.global_limit or counts[1] >= self.source_limit:
                        result = Reservation('limited', submission_id, day+86400-now)
                    else:
                        db.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?)', (submission_id,digest,source,now,now+30,'sending'))
                        result = Reservation('reserved', submission_id)
                db.execute('COMMIT')
                return result
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def finish(self, submission_id, outcome):
        if outcome not in ('accepted','failed_safe','unknown'):
            raise ValueError('invalid_outcome')
        now = int(self.clock())
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._expire(db, now)
            db.execute("UPDATE submissions SET state=? WHERE id=? AND state='sending'", (outcome,submission_id))
            db.execute('COMMIT')

    def cleanup(self):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._expire(db, int(self.clock()))
            db.execute('COMMIT')
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
