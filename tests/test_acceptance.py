import json
import os
import threading
import unittest
from app.client import analysis
from app.server import make_server
from app.study_store import load_case

# The analysis route is now wired end to end, so these tests run by default.
# Set RUN_ACCEPTANCE=0 to skip them in constrained environments.
ENABLED = os.environ.get('RUN_ACCEPTANCE', '1') != '0'


@unittest.skipUnless(ENABLED, '分析消费接口验收测试已按环境变量关闭')
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
        self.assertEqual(result['diagnostics']['graph_version'],
                         load_case('standard')['graph_version'])
        json.dumps(result, allow_nan=False)

    def test_information_limits_are_visible(self):
        result = analysis(self.base, 'edge')
        self.assertEqual(result['snapshot'], load_case('edge')['_snapshot'])
        self.assertTrue(result['diagnostics'])
        self.assertTrue(result['diagnostics']['information_limits']['not_liability_finding'])

    def test_opposite_hard_evidence_is_reported_as_incompatible(self):
        result = analysis(self.base, 'edge')
        self.assertEqual(result['compatibility']['status'], 'incompatible')
        self.assertIsNone(result['posterior'])
        self.assertEqual(result['compatibility']['review_evidence'], ['arrival', 'conflict'])

    def test_single_node_prior_is_not_changed_without_evidence(self):
        result = analysis(self.base, 'single')
        self.assertEqual(result['compatibility']['status'], 'compatible')
        self.assertAlmostEqual(result['posterior']['damage'][0][0], 0.75)
        self.assertAlmostEqual(result['posterior']['damage'][0][1], 0.75)
        self.assertAlmostEqual(result['posterior']['damage'][1][0], 0.25)
        self.assertAlmostEqual(result['posterior']['damage'][1][1], 0.25)

    def test_intervals_and_test_values_survive_the_round_trip(self):
        result = analysis(self.base, 'interval')
        damage = result['posterior']['damage']
        self.assertLess(damage[1][0], damage[1][1])
        self.assertGreater(damage[1][1], 0.0)
        self.assertEqual(result['test_value']['recommended_test'], 'damage_scan')
        self.assertEqual(result['diagnostics']['parameter_uncertainty']['representation'],
                         '每行独立的 [lower, upper] + 行和为一约束；条件概率行之间独立')

    def test_exclusion_and_budget_options(self):
        result = analysis(self.base, 'interval', exclude_evidence=['sensor'], budget=0.5)
        change = result['diagnostics']['evidence_exclusion']
        self.assertEqual(change['excluded_evidence'], ['sensor'])
        self.assertIn('posterior_max_abs_change', change)
        self.assertEqual(result['test_value']['budget'], 0.5)
        self.assertEqual({row['id'] for row in result['test_value']['tests']}, {'thermal_trace'})

    def test_bad_evidence_id_is_a_client_error(self):
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as caught:
            analysis(self.base, 'standard', exclude_evidence=['missing'])
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
