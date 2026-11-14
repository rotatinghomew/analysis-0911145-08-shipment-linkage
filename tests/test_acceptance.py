import json
import os
import threading
import unittest
from app.client import analysis
from app.server import make_server
from app.study_store import load_case


@unittest.skipUnless(os.environ.get('RUN_ACCEPTANCE') == '1', '分析消费接口尚未接入')
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

    def test_consumer_contract_and_provenance(self):
        result = analysis(self.base)
        self.assertEqual(result['snapshot'], load_case('standard')['_snapshot'])
        for field in ['posterior', 'compatibility', 'test_value', 'diagnostics']:
            self.assertIn(field, result)
        json.dumps(result, allow_nan=False)

    def test_information_limits_are_visible(self):
        result = analysis(self.base, 'edge')
        self.assertEqual(result['snapshot'], load_case('edge')['_snapshot'])
        self.assertTrue(result['diagnostics'])

    def test_opposite_hard_evidence_is_reported_as_incompatible(self):
        result = analysis(self.base, 'edge')
        self.assertEqual(result['compatibility']['status'], 'incompatible')

    def test_single_node_prior_is_not_changed_without_evidence(self):
        result = analysis(self.base, 'single')
        self.assertEqual(result['compatibility']['status'], 'compatible')
        self.assertAlmostEqual(result['posterior']['damage'][0][0], 0.75)
        self.assertAlmostEqual(result['posterior']['damage'][0][1], 0.75)
        self.assertAlmostEqual(result['posterior']['damage'][1][0], 0.25)
        self.assertAlmostEqual(result['posterior']['damage'][1][1], 0.25)
