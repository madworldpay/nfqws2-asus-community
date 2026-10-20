import hashlib
import multiprocessing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'support-relay/src'))
from nfqws_support.store import RelayStore


def digest(n):
    return hashlib.sha256(str(n).encode()).hexdigest()


def reserve_worker(path, barrier, result, n):
    store = RelayStore(path, b'x'*32, lambda: 1700000000)
    barrier.wait()
    result.put(store.reserve(str(uuid.uuid4()), digest(n), '192.0.2.4').decision)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'metadata.sqlite'
        self.now = 1700000000
        self.store = RelayStore(self.path, b'x'*32, lambda: self.now)

    def reserve(self, n, source='192.0.2.4', submission=None):
        return self.store.reserve(submission or str(uuid.uuid4()), digest(n), source)

    def test_two_processes_cannot_reserve_two_smtp_attempts(self):
        ctx = multiprocessing.get_context('fork')
        barrier, result = ctx.Barrier(2), ctx.Queue()
        children = [ctx.Process(target=reserve_worker, args=(self.path, barrier, result, n)) for n in [1, 2]]
        for child in children: child.start()
        for child in children:
            child.join(10)
            self.assertEqual(child.exitcode, 0)
        self.assertEqual(sorted([result.get(timeout=2), result.get(timeout=2)]), ['busy', 'reserved'])

    def test_source_and_global_quota_count_failed_attempts(self):
        for n in range(3):
            r = self.reserve(n)
            self.assertEqual(r.decision, 'reserved')
            self.store.finish(r.submission_id, 'failed_safe')
        self.assertEqual(self.reserve(4).decision, 'limited')
        for n in range(3, 20):
            r = self.reserve(n, f'198.51.100.{n}')
            self.assertEqual(r.decision, 'reserved')
            self.store.finish(r.submission_id, 'failed_safe')
        self.assertEqual(self.reserve(21, '203.0.113.1').decision, 'limited')
        self.now = (self.now // 86400 + 1) * 86400
        self.assertEqual(self.reserve(22).decision, 'reserved')

    def test_accepted_unknown_and_sending_digests_cannot_be_resent(self):
        for n, terminal in enumerate(['accepted', 'unknown']):
            r = self.reserve(n)
            self.store.finish(r.submission_id, terminal)
            self.assertEqual(self.reserve(n, submission=r.submission_id).decision, terminal)
            self.assertEqual(self.reserve(n).decision, terminal)
        r = self.reserve(3)
        self.assertEqual(self.reserve(3).decision, 'busy')
        self.now += 31
        self.assertEqual(self.reserve(3).decision, 'unknown')
        # A late worker cannot overwrite the ambiguous terminal record.
        self.store.finish(r.submission_id, 'failed_safe')
        self.assertEqual(self.reserve(3).decision, 'unknown')

    def test_id_conflict_and_failed_safe_require_new_explicit_id(self):
        r = self.reserve(1)
        self.store.finish(r.submission_id, 'failed_safe')
        self.assertEqual(self.reserve(1, submission=r.submission_id).decision, 'failed_safe')
        self.assertEqual(self.reserve(2, submission=r.submission_id).decision, 'id_conflict')
        self.assertEqual(self.reserve(1).decision, 'reserved')

    def test_metadata_has_no_raw_source_or_body_and_expires(self):
        r = self.reserve('PRIVATE_CANARY')
        self.store.finish(r.submission_id, 'accepted')
        with sqlite3.connect(self.path) as db:
            for path in self.path.parent.glob('metadata.sqlite*'):
                raw = path.read_bytes()
                self.assertNotIn(b'192.0.2.4', raw)
                self.assertNotIn(b'PRIVATE_CANARY', raw)
            self.assertEqual(db.execute('select count(*) from submissions').fetchone()[0], 1)
        self.now += 7 * 86400 + 1
        self.store.cleanup()
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('select count(*) from submissions').fetchone()[0], 0)

    def test_invalid_public_identifiers_cannot_enter_storage(self):
        for sid, value in [('PRIVATE_CANARY', digest(1)), (str(uuid.uuid4()), 'PRIVATE_CANARY')]:
            with self.assertRaises(ValueError):
                self.store.reserve(sid, value, '192.0.2.1')

    def test_hourly_cleanup_has_margin_before_seven_day_retention_bound(self):
        r=self.reserve(1); self.store.finish(r.submission_id,'accepted')
        self.now += 7*86400-3600+1
        self.store.cleanup()
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('select count(*) from submissions').fetchone()[0],0)
