import copy
import itertools
import json
import math
import unittest

from app import inference
from app.study import validate
from app.study_store import load_case


def case(nodes, evidence=(), actions=(), tests=(), budget=None, version='test-1'):
    return {
        'kind': 'diagnosis',
        'graph_version': version,
        'nodes': list(nodes),
        'evidence': list(evidence),
        'actions': list(actions),
        'available_tests': list(tests),
        'budget': budget,
    }


def root(identifier, states, probabilities):
    return {'id': identifier, 'states': states, 'parents': [],
            'rows': [{'when': {}, 'probabilities': probabilities}]}


def child(identifier, states, parents, rows):
    return {'id': identifier, 'states': states, 'parents': parents, 'rows': rows}


class ExactUpdateTests(unittest.TestCase):
    def test_chain_posterior_matches_hand_calculation(self):
        mechanism = case([
            root('warm', ['no', 'yes'], [[0.5, 0.5], [0.5, 0.5]]),
            child('logger', ['clear', 'warning'], ['warm'], [
                {'when': {'warm': 'no'}, 'probabilities': [[0.9, 0.9], [0.1, 0.1]]},
                {'when': {'warm': 'yes'}, 'probabilities': [[0.2, 0.2], [0.8, 0.8]]},
            ]),
            child('damage', ['no', 'yes'], ['warm'], [
                {'when': {'warm': 'no'}, 'probabilities': [[0.9, 0.9], [0.1, 0.1]]},
                {'when': {'warm': 'yes'}, 'probabilities': [[0.1, 0.1], [0.9, 0.9]]},
            ]),
        ], evidence=[
            {'id': 'log', 'node': 'logger', 'likelihood': [0, 1]},
            {'id': 'look', 'node': 'damage', 'likelihood': [0, 1]},
        ])
        result = inference.analyze(mechanism)
        # Joint: P(no) = 0.5 * 0.1 * 0.1, P(yes) = 0.5 * 0.8 * 0.9.
        self.assertAlmostEqual(result['posterior']['warm'][0][0], 0.005 / 0.365, places=11)
        self.assertAlmostEqual(result['posterior']['warm'][1][0], 0.36 / 0.365, places=11)
        # Both observations are children of the same cause.  Treating them as
        # two independent votes would leave warm at 0.5; the graph keeps their
        # dependence instead.
        self.assertNotAlmostEqual(result['posterior']['warm'][1][0], 0.5, places=3)

    def test_interval_bounds_are_extrema_over_feasible_rows(self):
        mechanism = case([
            root('damage', ['no', 'yes'], [[0.4, 0.7], [0.3, 0.6]]),
        ], evidence=[{'id': 'look', 'node': 'damage', 'likelihood': [1, 3]}],
            actions=[{'id': 'accept', 'loss_by_damage': [0, 20]},
                     {'id': 'hold', 'loss_by_damage': [10, 10]}])
        result = inference.analyze(mechanism)
        # The row constraint leaves P(damage = yes) feasible on [0.3, 0.6], and
        # P(yes | look) = 3p / (1 + 2p) is increasing in p.
        self.assertAlmostEqual(result['posterior']['damage'][1][0], 0.9 / 1.6, places=11)
        self.assertAlmostEqual(result['posterior']['damage'][1][1], 1.8 / 2.2, places=11)
        self.assertAlmostEqual(result['posterior']['damage'][0][1], 0.7 / 1.6, places=11)
        # The per-state extrema come from different feasible completions, so
        # they do not form one normalized distribution.
        self.assertGreater(result['posterior']['damage'][0][1]
                           + result['posterior']['damage'][1][1], 1.0)

    def test_single_node_prior_without_evidence_is_untouched(self):
        result = inference.analyze(load_case('single'))
        self.assertEqual(result['compatibility']['status'], 'compatible')
        self.assertEqual(result['posterior']['damage'], [[0.75, 0.75], [0.25, 0.25]])

    def test_multiedge_graph_is_enumerated_exactly(self):
        mechanism = case([
            root('a', ['no', 'yes'], [[0.6, 0.6], [0.4, 0.4]]),
            root('b', ['no', 'yes'], [[0.3, 0.3], [0.7, 0.7]]),
            child('damage', ['no', 'yes'], ['a', 'b'], [
                {'when': {'a': 'no', 'b': 'no'}, 'probabilities': [[0.9, 0.9], [0.1, 0.1]]},
                {'when': {'a': 'no', 'b': 'yes'}, 'probabilities': [[0.5, 0.5], [0.5, 0.5]]},
                {'when': {'a': 'yes', 'b': 'no'}, 'probabilities': [[0.4, 0.4], [0.6, 0.6]]},
                {'when': {'a': 'yes', 'b': 'yes'}, 'probabilities': [[0.1, 0.1], [0.9, 0.9]]},
            ]),
        ], evidence=[{'id': 'look', 'node': 'damage', 'likelihood': [1, 4]}])
        result = inference.analyze(mechanism)
        joint = {(a, b): pa * pb for a, pa in zip(('no', 'yes'), (0.6, 0.4))
                 for b, pb in zip(('no', 'yes'), (0.3, 0.7))}
        damage = {('no', 'no'): 0.1, ('no', 'yes'): 0.5,
                  ('yes', 'no'): 0.6, ('yes', 'yes'): 0.9}
        weights = {}
        for (a, b), probability in joint.items():
            for state, value in (('no', 1 - damage[(a, b)]), ('yes', damage[(a, b)])):
                weights[state] = weights.get(state, 0.0) + probability * value
        denominator = weights['no'] * 1 + weights['yes'] * 4
        self.assertAlmostEqual(result['posterior']['damage'][1][0],
                               weights['yes'] * 4 / denominator, places=11)


class CompatibilityTests(unittest.TestCase):
    def test_opposite_observations_identify_minimal_review_set(self):
        result = inference.analyze(load_case('edge'))
        self.assertEqual(result['compatibility']['status'], 'incompatible')
        self.assertEqual(result['compatibility']['reason'], 'zero_support')
        self.assertIsNone(result['posterior'])
        self.assertIsNone(result['test_value'])
        self.assertEqual(result['compatibility']['review_evidence'], ['arrival', 'conflict'])
        self.assertEqual(result['diagnostics']['review_evidence'], ['arrival', 'conflict'])
        self.assertTrue(result['diagnostics']['conflicts'])

    def test_no_renormalised_posterior_is_offered_on_conflict(self):
        result = inference.analyze(load_case('edge'))
        json.dumps(result, allow_nan=False)
        self.assertNotIn('posterior', [key for key, value in result.items() if value is not None
                                       and key == 'posterior'])

    def test_graph_error_is_distinguished_from_zero_support(self):
        broken = copy.deepcopy(load_case('standard'))
        broken['nodes'][2]['rows'][0]['probabilities'] = [[0.9, 0.9], [0.9, 0.9]]
        result = inference.analyze(broken)
        self.assertEqual(result['compatibility']['status'], 'incompatible')
        self.assertEqual(result['compatibility']['reason'], 'graph_invalid')
        self.assertIn('graph_error', result['diagnostics'])

    def test_same_source_cannot_be_counted_twice(self):
        duplicated = copy.deepcopy(load_case('interval'))
        duplicated['evidence'][1]['source'] = duplicated['evidence'][0]['source']
        result = inference.analyze(duplicated)
        self.assertEqual(result['compatibility']['reason'], 'graph_invalid')
        self.assertIn('同一来源', result['compatibility']['message'])

    def test_unknown_exclusion_is_rejected(self):
        with self.assertRaises(ValueError):
            inference.analyze(load_case('standard'), exclude_evidence=['missing'])

    def test_negative_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            inference.analyze(load_case('standard'), budget=-1)

    def test_oversized_enumeration_is_rejected_not_sampled(self):
        # Four unconstrained binary roots leave 2**4 vertices per root row and
        # 2**16 joint states, beyond the local enumeration budget.
        roots = [root('r%d' % index, ['no', 'yes'], [[0, 1], [0, 1]]) for index in range(4)]
        parents = [item['id'] for item in roots]
        rows = []
        for combo in itertools.product(('no', 'yes'), repeat=4):
            rows.append({'when': dict(zip(parents, combo)),
                         'probabilities': [[0.6, 0.9], [0.1, 0.4]]})
        graph = roots + [child('damage', ['no', 'yes'], parents, rows)]
        result = inference.analyze(case(graph, actions=[
            {'id': 'accept', 'loss_by_damage': [0, 20]}]))
        self.assertEqual(result['compatibility']['status'], 'incompatible')
        self.assertEqual(result['compatibility']['reason'], 'graph_invalid')
        self.assertIn('规模', result['compatibility']['message'])


class SensitivityTests(unittest.TestCase):
    def test_exclusion_reports_what_changed(self):
        full = inference.analyze(load_case('interval'))
        reduced = inference.analyze(load_case('interval'), exclude_evidence=['sensor'])
        change = reduced['diagnostics']['evidence_exclusion']
        self.assertEqual(change['excluded_evidence'], ['sensor'])
        self.assertEqual(change['remaining_evidence'], ['arrival'])
        self.assertEqual(change['posterior_before'], full['posterior'])
        self.assertEqual(reduced['diagnostics']['evidence_sources'][1]['status'], 'excluded')
        changed = change['posterior_max_abs_change']
        self.assertGreater(changed['logger'], 0.01)
        self.assertIn('decision_changed', change)

    def test_exclusion_can_restore_compatibility(self):
        result = inference.analyze(load_case('edge'), exclude_evidence=['conflict'])
        self.assertEqual(result['compatibility']['status'], 'compatible')
        self.assertEqual(result['diagnostics']['evidence_exclusion']['baseline_status'], 'incompatible')
        self.assertIsNone(result['diagnostics']['evidence_exclusion']['decision_before'])

    def test_exclusion_is_visible_in_sources(self):
        result = inference.analyze(load_case('interval'), exclude_evidence=['arrival', 'sensor'])
        statuses = {row['id']: row['status'] for row in result['diagnostics']['evidence_sources']}
        self.assertEqual(set(statuses.values()), {'excluded'})
        self.assertEqual(result['compatibility']['status'], 'compatible')


class TestValueTests(unittest.TestCase):
    def setUp(self):
        # A single 50/50 damage node.  Both actions cost 10 per batch before a
        # test; a perfect scan costs 1, so its value is 10 - 5 - 1 = 4.
        self.mechanism = case([
            root('damage', ['no', 'yes'], [[0.5, 0.5], [0.5, 0.5]]),
        ], actions=[
            {'id': 'accept', 'loss_by_damage': [0, 20]},
            {'id': 'hold', 'loss_by_damage': [10, 10]},
        ], tests=[
            {'id': 'scan', 'node': 'damage', 'cost': 1,
             'probabilities': [[1, 0], [0, 1]]},
            {'id': 'coarse', 'node': 'damage', 'cost': 1,
             'probabilities': [[0.6, 0.4], [0.4, 0.6]]},
            {'id': 'expensive', 'node': 'damage', 'cost': 50,
             'probabilities': [[1, 0], [0, 1]]},
        ], budget=5)

    def test_value_of_information_is_loss_reduction_net_of_cost(self):
        result = inference.analyze(self.mechanism)
        tests = {row['id']: row for row in result['test_value']['tests']}
        self.assertAlmostEqual(tests['scan']['decision_loss_reduction_range'][0], 5.0, places=10)
        self.assertAlmostEqual(tests['scan']['min_net_value_over_completions'], 4.0, places=10)
        self.assertGreater(tests['scan']['min_net_value_over_completions'],
                           tests['coarse']['min_net_value_over_completions'])
        self.assertEqual(result['test_value']['recommended_test'], 'scan')

    def test_budget_excludes_unreachable_tests(self):
        result = inference.analyze(self.mechanism)
        unavailable = {row['id']: row for row in result['test_value']['unavailable_tests']}
        self.assertEqual(unavailable['expensive']['reason'], 'over_budget')
        self.assertNotIn('expensive', [row['id'] for row in result['test_value']['tests']])

    def test_zero_budget_has_no_recommendation(self):
        result = inference.analyze(load_case('interval'), budget=0)
        self.assertEqual(result['test_value']['tests'], [])
        self.assertIsNone(result['test_value']['recommended_test'])

    def test_reported_values_are_finite_and_serializable(self):
        result = inference.analyze(load_case('interval'))
        json.dumps(result, allow_nan=False)
        for row in result['test_value']['tests']:
            for key in ('cost', 'min_net_value_over_completions'):
                self.assertTrue(math.isfinite(row[key]))


class ProvenanceTests(unittest.TestCase):
    def test_snapshot_version_and_sources_are_preserved(self):
        study = load_case('interval')
        result = inference.analyze(study)
        self.assertEqual(result['snapshot'], study['_snapshot'])
        self.assertEqual(result['diagnostics']['graph_version'], study['graph_version'])
        self.assertEqual([row['id'] for row in result['diagnostics']['evidence_sources']],
                         [row['id'] for row in study['evidence']])
        self.assertEqual([row['source'] for row in result['diagnostics']['evidence_sources']],
                         [row['source'] for row in study['evidence']])

    def test_decision_basis_is_recorded(self):
        result = inference.analyze(load_case('interval'))
        basis = result['diagnostics']['decision_basis']
        self.assertEqual(basis['action'], result['test_value']['baseline']['action'])
        self.assertIn('expected_loss_bounds', basis)
        self.assertEqual(basis['criterion'],
                         'minimax_expected_loss_over_feasible_cpt_completions')

    def test_interpretation_limits_are_stated(self):
        limits = inference.analyze(load_case('standard'))['diagnostics']['information_limits']
        self.assertTrue(limits['not_liability_finding'])
        self.assertTrue(limits['not_causal_effect_estimate'])
        self.assertTrue(limits['conditional_inference_only'])

    def test_all_study_cases_validate(self):
        for name in ('standard', 'single', 'edge', 'interval'):
            validate(load_case(name))


if __name__ == '__main__':
    unittest.main()
