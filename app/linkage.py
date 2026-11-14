from collections import defaultdict
from app.review import hard_decisions
from app.metrics import confirmed_metrics
from app.store import unique


def candidate_components(case):
    orders = unique(case['orders'], 'id')
    receipts = unique(case['receipts'], 'id')
    adjacency = defaultdict(set)
    for edge in case['candidates']:
        if edge['order'] not in orders or edge['receipt'] not in receipts:
            raise ValueError('candidate endpoint missing')
        left, right = 'o:' + edge['order'], 'r:' + edge['receipt']
        adjacency[left].add(right)
        adjacency[right].add(left)
    remaining = set(adjacency)
    components = []
    while remaining:
        pending = [min(remaining)]
        visited = set()
        while pending:
            current = pending.pop()
            if current not in visited:
                visited.add(current)
                pending.extend(adjacency[current] - visited)
        remaining -= visited
        components.append(sorted(visited))
    return components


def confirmed_matches(case):
    decisions = hard_decisions(case['reviews'])
    matches = [key for key, action in decisions.items() if action == 'accept']
    orders = unique(case['orders'], 'id')
    receipts = unique(case['receipts'], 'id')
    used_orders, used_receipts = defaultdict(int), defaultdict(int)
    for order_id, receipt_id in matches:
        used_orders[order_id] += receipts[receipt_id]['units_consumed']
        used_receipts[receipt_id] += 1
    if any(used_orders[key] > orders[key]['slots'] for key in used_orders):
        raise ValueError('confirmed order capacity exceeded')
    if any(used_receipts[key] > receipts[key]['parcel_capacity'] for key in used_receipts):
        raise ValueError('confirmed receipt consumed twice')
    return matches


def preview(case):
    try:
        matches = confirmed_matches(case)
        error = None
    except ValueError as caught:
        matches, error = [], str(caught)
    return {'snapshot': case['_snapshot'], 'candidate_components': candidate_components(case),
            'confirmed': matches, 'review_error': error,
            'confirmed_metrics': confirmed_metrics(case['orders'], case['receipts'], matches),
            'unresolved_are_not_failures': True}
