import os
import threading
import unittest

from app.client import analysis
from app.server import make_server
from app.store import load_case


@unittest.skipUnless(os.environ.get('RUN_ACCEPTANCE') == '1', 'new analysis feature not enabled')
class AnalysisContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server()
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.worker.join(timeout=3)
        cls.server.server_close()

    def test_result_has_consumer_fields_and_provenance(self):
        result = analysis(self.base)
        self.assertEqual(result['snapshot'], load_case('standard')['_snapshot'])
        for field in ['matches', 'unmatched', 'metrics', 'review_queue', 'diagnostics']:
            self.assertIn(field, result)
        self.assertTrue(result['diagnostics'])

    def test_edge_case_is_not_silently_treated_as_standard(self):
        standard = analysis(self.base)
        edge = analysis(self.base, 'edge')
        self.assertNotEqual(standard['snapshot'], edge['snapshot'])
        self.assertTrue(edge['diagnostics'])

    def test_receipt_cannot_be_allocated_twice_and_confirmation_survives(self):
        result = analysis(self.base)
        pairs = [(row['order'], row['receipt']) for row in result['matches']]
        self.assertIn(('o0', 'r0'), pairs)
        self.assertNotIn(('o1', 'r0'), pairs)
        receipts = [pair[1] for pair in pairs]
        self.assertEqual(len(receipts), len(set(receipts)))

    def test_conflicting_reviews_do_not_produce_a_clean_assignment(self):
        result = analysis(self.base, 'edge')
        self.assertTrue(result['diagnostics'])
        self.assertFalse(result['matches'])
