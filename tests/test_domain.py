import unittest
from app.linkage import confirmed_matches, candidate_components
from app.metrics import confirmed_metrics
from app.store import load_case


class LinkageTests(unittest.TestCase):
    def test_confirmed_match_not_best_score_overwrite(self):
        self.assertEqual(confirmed_matches(load_case('standard')), [('o0', 'r0')])

    def test_conflicting_review_is_not_silent(self):
        with self.assertRaises(ValueError):
            confirmed_matches(load_case('edge'))

    def test_unresolved_slots_remain_in_denominator(self):
        case = load_case('standard')
        metrics = confirmed_metrics(case['orders'], case['receipts'], confirmed_matches(case))
        self.assertGreater(sum(row['expected_slots'] for row in metrics.values()),
                           sum(row['confirmed_units'] for row in metrics.values()))

    def test_graph_reaches_competing_orders(self):
        components = candidate_components(load_case('standard'))
        self.assertTrue(any('o:o0' in component and 'r:r0' in component for component in components))
