def hard_decisions(reviews):
    decisions = {}
    revisions = set()
    for row in sorted(reviews, key=lambda item: item['revision']):
        if row['revision'] in revisions:
            raise ValueError('duplicate review revision')
        revisions.add(row['revision'])
        key = (row['order'], row['receipt'])
        if row['action'] not in ('accept', 'reject'):
            raise ValueError('unknown review decision')
        previous = decisions.get(key)
        if previous is not None and previous != row['action']:
            raise ValueError('conflicting immutable review decisions')
        decisions[key] = row['action']
    return decisions
