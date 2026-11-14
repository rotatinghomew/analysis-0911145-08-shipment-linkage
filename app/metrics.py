from collections import defaultdict


def confirmed_metrics(orders, receipts, matches):
    by_order = {row['id']: row for row in orders}
    by_receipt = {row['id']: row for row in receipts}
    result = defaultdict(lambda: {'expected_slots': 0, 'confirmed_units': 0, 'on_time_units': 0})
    for order in orders:
        result[order['merchant']]['expected_slots'] += order['slots']
    for order_id, receipt_id in matches:
        order = by_order[order_id]
        receipt = by_receipt[receipt_id]
        group = result[order['merchant']]
        group['confirmed_units'] += receipt['units_consumed']
        if receipt['arrived_at'] <= order['promised_at']:
            group['on_time_units'] += receipt['units_consumed']
    return dict(result)
