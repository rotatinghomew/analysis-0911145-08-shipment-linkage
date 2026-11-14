import itertools
import math
from app.study_schema import rows_by_id, probability


def validate(case):
    nodes = rows_by_id(case['nodes'])
    ordered = []
    remaining = set(nodes)
    while remaining:
        ready = sorted(key for key in remaining if set(nodes[key]['parents']) <= set(ordered))
        if not ready:
            raise ValueError('概率图存在环或未知父节点')
        ordered.extend(ready)
        remaining.difference_update(ready)
    for node in nodes.values():
        if len(set(node['states'])) != len(node['states']) or not node['states']:
            raise ValueError('状态定义不完整')
        expected = set(itertools.product(*(nodes[parent]['states'] for parent in node['parents'])))
        observed = set()
        for row in node['rows']:
            if set(row['when']) != set(node['parents']):
                raise ValueError('条件表父节点范围不一致')
            assignment = tuple(row['when'][parent] for parent in node['parents'])
            if assignment in observed:
                raise ValueError('条件表重复')
            observed.add(assignment)
            bounds = row['probabilities']
            if len(bounds) != len(node['states']):
                raise ValueError('状态概率缺失')
            for lower, upper in bounds:
                if probability(lower) > probability(upper):
                    raise ValueError('条件概率区间逆序')
            if sum(bound[0] for bound in bounds) > 1 + 1e-9 or sum(bound[1] for bound in bounds) < 1 - 1e-9:
                raise ValueError('条件概率无法归一')
        if observed != expected:
            raise ValueError('条件表组合不完整')
    for evidence in case['evidence']:
        if len(evidence['likelihood']) != len(nodes[evidence['node']]['states']):
            raise ValueError('证据状态不一致')
        for value in evidence['likelihood']:
            if not math.isfinite(value) or value < 0:
                raise ValueError('证据似然必须非负且有限')
    return nodes, ordered


def preview(case):
    nodes, ordered = validate(case)
    return {'snapshot': case['_snapshot'], 'graph_version': case['graph_version'],
            'topological_order': ordered, 'state_counts': {key: len(node['states']) for key, node in nodes.items()},
            'evidence_ids': [row['id'] for row in case['evidence']], 'descriptive_only': True}
