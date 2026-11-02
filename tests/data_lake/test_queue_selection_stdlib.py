import tempfile
import unittest
from datalake.identity import Job
from datalake.storage import Lake


class DatasetSelectionTests(unittest.TestCase):
    def test_dataset_selection_intersects_sources_without_changing_other_jobs(self):
        with tempfile.TemporaryDirectory() as root:
            lake=Lake(root)
            unrelated=Job('A','other','raw','https://example.invalid/1',priority=0)
            target=Job('A','chosen','raw','https://example.invalid/2',priority=20)
            other_source=Job('B','chosen','raw','https://example.invalid/3',priority=0)
            lake.add([unrelated,target,other_source])
            claimed=lake.claim(['A'],datasets=['chosen'])
            self.assertEqual(claimed.id,target.id)
            with lake.db() as db:
                rows={r['id']:(r['state'],r['attempts'],r['priority']) for r in db.execute('SELECT * FROM jobs')}
            self.assertEqual(rows[unrelated.id],('pending',0,0))
            self.assertEqual(rows[other_source.id],('pending',0,0))
            self.assertIsNone(lake.claim(['A'],datasets=['chosen']))
            self.assertEqual(lake.claim().id,min(unrelated.id,other_source.id))
