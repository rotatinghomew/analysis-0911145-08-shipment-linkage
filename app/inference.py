"""Exact conditional inference for the discrete mechanism graph.

Each conditional-probability row is a polytope: every state probability lies
in [lower, upper] and the row sums to one.  A *completion* fixes one feasible
vector for every row.  Node posterior bounds are extrema over all feasible
completions.  For a ratio of multilinear joint weights, every extremum over
the product of row polytopes is attained at a tuple of row vertices, so
enumerating vertices is exact rather than a sample.

Evidence likelihoods are factors attached to graph nodes.  They multiply
conditionally on the node state, so observations that share an upstream cause
remain dependent through the graph; they are not independent votes.
"""

import itertools
import math

TOL = 1e-9
MAX_COMPLETIONS = 100000
MAX_JOINT_STATES = 100000
MAX_CONFLICT_EVIDENCE = 16
MAX_WORK = 15000000


class GraphInvalid(ValueError):
    """The mechanism graph, actions, tests or evidence schema is invalid."""


def _number(value, what, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GraphInvalid(what + ' 必须是有限数值')
    value = float(value)
    if nonnegative and value < 0:
        raise GraphInvalid(what + ' 不能为负')
    return value


def _probability(value, what):
    value = _number(value, what)
    if not 0 <= value <= 1:
        raise GraphInvalid(what + ' 必须在零到一之间')
    return value


def _clean(value):
    if abs(value) < 5e-13:
        return 0.0
    value = round(float(value), 12)
    return 0.0 if value == 0 else value


def row_vertices(bounds):
    """All vertices of {sum(p) = 1, lower <= p <= upper}."""
    lower = [_probability(low, '条件概率下界') for low, _ in bounds]
    upper = [_probability(high, '条件概率上界') for _, high in bounds]
    for low, high in zip(lower, upper):
        if low > high:
            raise GraphInvalid('条件概率区间逆序')
    if sum(lower) > 1 + TOL or sum(upper) < 1 - TOL:
        raise GraphInvalid('条件概率无法归一')
    size = len(bounds)
    found = {}

    def remember(point):
        found[tuple(_clean(value) for value in point)] = list(point)

    # A vertex of the box/plane intersection has all but at most one
    # coordinate at a bound.  Enumerating the one free coordinate is exact.
    for free in range(size):
        others = [index for index in range(size) if index != free]
        for bits in itertools.product((0, 1), repeat=len(others)):
            point = [None] * size
            for position, coordinate in enumerate(others):
                point[coordinate] = upper[coordinate] if bits[position] else lower[coordinate]
            remainder = 1.0 - math.fsum(point[index] for index in others)
            if lower[free] - TOL <= remainder <= upper[free] + TOL:
                point[free] = min(1.0, max(0.0, remainder))
                remember(point)
    # Degenerate rows where every coordinate is fixed.
    point = list(lower)
    if abs(math.fsum(point) - 1) <= TOL:
        remember(point)
    if not found:
        raise GraphInvalid('条件概率区间没有可行取值')
    return list(found.values())


def _state_capacity(lower, upper, state):
    """Largest feasible mass on one state (0 when the state is unreachable)."""
    slack = 1.0 - math.fsum(lower[index] for index in range(len(lower)) if index != state)
    return min(upper[state], slack)


def _row_key(node, parent_indices):
    return (node, tuple(parent_indices))


def validate_case(case):
    """Validate the graph plus the decision/test schema."""
    if not isinstance(case, dict):
        raise GraphInvalid('分析资料必须是对象')
    try:
        return _validate_case(case)
    except GraphInvalid:
        raise
    except (ValueError, KeyError, TypeError, IndexError) as error:
        raise GraphInvalid('分析资料结构无效：' + str(error)) from None


def _validate_case(case):
    try:
        from app.study import validate
        nodes, ordered = validate(case)
    except (ValueError, KeyError, TypeError) as error:
        raise GraphInvalid(str(error)) from None

    evidence = []
    seen_evidence = set()
    seen_sources = {}
    for row in case['evidence']:
        identifier = row['id']
        if not isinstance(identifier, str) or not identifier:
            raise GraphInvalid('证据标识无效')
        if identifier in seen_evidence:
            raise GraphInvalid('重复证据标识：' + identifier)
        seen_evidence.add(identifier)
        if row['node'] not in nodes:
            raise GraphInvalid('证据节点不存在：' + str(row['node']))
        source = row.get('source')
        if source is not None:
            if source in seen_sources:
                raise GraphInvalid(
                    '证据 %s 与 %s 声明了同一来源 %s；同一来源不能重复当作独立观测，请先合并。'
                    % (seen_sources[source], identifier, source))
            seen_sources[source] = identifier
        values = [_number(value, '证据似然', nonnegative=True) for value in row['likelihood']]
        if len(values) != len(nodes[row['node']]['states']):
            raise GraphInvalid('证据状态不一致')
        evidence.append({'id': identifier, 'node': row['node'], 'likelihood': values})

    rows = []
    upper_map = {}
    capacity = {}
    for node_name in ordered:
        node = nodes[node_name]
        for row in node['rows']:
            parent_indices = tuple(nodes[parent]['states'].index(row['when'][parent])
                                   for parent in node['parents'])
            key = _row_key(node_name, parent_indices)
            vertices = row_vertices(row['probabilities'])
            lower = [float(low) for low, _ in row['probabilities']]
            upper = [float(high) for _, high in row['probabilities']]
            rows.append((key, vertices))
            upper_map[key] = upper
            capacity[key] = [_state_capacity(lower, upper, state) for state in range(len(upper))]

    assignments = []
    total_states = 1
    for node_name in ordered:
        total_states *= len(nodes[node_name]['states'])
    if total_states > MAX_JOINT_STATES:
        raise GraphInvalid('联合状态数过多，无法在本地工作台内枚举')
    for combo in itertools.product(*(range(len(nodes[name]['states'])) for name in ordered)):
        assignments.append(dict(zip(ordered, combo)))

    actions = []
    seen_actions = set()
    damage_states = nodes['damage']['states'] if 'damage' in nodes else None
    for row in case.get('actions', []):
        identifier = row['id']
        if not isinstance(identifier, str) or not identifier:
            raise GraphInvalid('处置动作标识无效')
        if identifier in seen_actions:
            raise GraphInvalid('重复处置动作标识：' + identifier)
        seen_actions.add(identifier)
        if damage_states is None:
            raise GraphInvalid('处置损失需要 damage 节点')
        loss = row['loss_by_damage']
        if not isinstance(loss, list) or len(loss) != len(damage_states):
            raise GraphInvalid('处置损失状态数不一致')
        actions.append({
            'id': identifier,
            'loss_by_damage': [_number(value, '处置损失', nonnegative=True) for value in loss],
        })

    tests = []
    seen_tests = set()
    for row in case.get('available_tests', []):
        identifier = row['id']
        if not isinstance(identifier, str) or not identifier:
            raise GraphInvalid('补验标识无效')
        if identifier in seen_tests:
            raise GraphInvalid('重复补验标识：' + identifier)
        seen_tests.add(identifier)
        node_name = row['node']
        if node_name not in nodes:
            raise GraphInvalid('补验节点不存在：' + str(node_name))
        matrix = []
        width = None
        for line in row['probabilities']:
            if not isinstance(line, list) or not line:
                raise GraphInvalid('补验概率行无效')
            if width is None:
                width = len(line)
            if len(line) != width:
                raise GraphInvalid('补验报告状态数不一致')
            matrix.append([_probability(value, '补验概率') for value in line])
        if len(matrix) != len(nodes[node_name]['states']):
            raise GraphInvalid('补验真实状态数不一致')
        for line in matrix:
            if abs(math.fsum(line) - 1) > 1e-6:
                raise GraphInvalid('补验概率行必须归一')
        report_states = row.get('report_states')
        if report_states is not None and (not isinstance(report_states, list)
                                          or len(report_states) != width
                                          or len(set(report_states)) != width):
            raise GraphInvalid('补验报告状态定义无效')
        tests.append({
            'id': identifier,
            'node': node_name,
            'cost': _number(row['cost'], '补验成本', nonnegative=True),
            'probabilities': matrix,
            'report_states': list(report_states) if report_states is not None else list(range(width)),
        })

    return {
        'nodes': nodes,
        'ordered': ordered,
        'evidence': evidence,
        'rows': rows,
        'upper_map': upper_map,
        'capacity': capacity,
        'assignments': assignments,
        'actions': actions,
        'tests': tests,
        'graph_version': case.get('graph_version'),
        'kind': case.get('kind'),
    }


def _assignment_capacity(spec, assignment):
    total = 1.0
    for node_name in spec['ordered']:
        node = spec['nodes'][node_name]
        key = _row_key(node_name, tuple(assignment[parent] for parent in node['parents']))
        total *= spec['capacity'][key][assignment[node_name]]
        if total <= 0:
            return 0.0
    return total


def support_analysis(spec, evidence):
    """Check whether any graph state is compatible with all evidence.

    A state has support when every row can put positive mass on it and every
    included evidence factor is positive there.  When joint support is empty,
    minimal unsupported evidence subsets identify what needs review.

    Each observation is represented as a bitset over reachable graph states, so
    a subset is supported exactly when the intersection of its bitsets is
    non-empty.  This stays cheap even for large joint state spaces.
    """
    feasible = [assignment for assignment in spec['assignments']
                if _assignment_capacity(spec, assignment) > 0]
    size = len(evidence)
    bits = [0] * size
    for index, assignment in enumerate(feasible):
        for position, item in enumerate(evidence):
            if item['likelihood'][assignment[item['node']]] > 0:
                bits[position] |= 1 << index

    def supported(subset):
        if subset == 0:
            return bool(feasible)
        common = None
        for position in range(size):
            if subset & (1 << position):
                common = bits[position] if common is None else (common & bits[position])
                if common == 0:
                    return False
        return common != 0

    alone = [{'id': item['id'], 'supported_alone': supported(1 << index)}
             for index, item in enumerate(evidence)]

    if not feasible:
        return {'supported': False, 'alone': alone, 'conflicts': [{
            'evidence_ids': [],
            'nodes': [],
            'reason': 'graph_has_no_reachable_state',
            'message': '机理图没有任何正概率状态，需要先复核图本身。',
        }], 'review': []}
    if supported((1 << size) - 1):
        return {'supported': True, 'alone': alone, 'conflicts': [], 'review': []}

    minimal = []
    limited = size > MAX_CONFLICT_EVIDENCE
    widths = size if not limited else min(3, size)
    minimal_masks = []
    for width in range(1, widths + 1):
        for combination in itertools.combinations(range(size), width):
            subset = 0
            for index in combination:
                subset |= 1 << index
            if supported(subset):
                continue
            if any((previous & subset) == previous for previous in minimal_masks):
                continue
            minimal_masks.append(subset)
            minimal.append([evidence[index]['id'] for index in combination])

    review = sorted({identifier for group in minimal for identifier in group})
    conflicts = []
    for group in minimal:
        involved = set(group)
        if len(group) == 1:
            message = '该观测在可行机理状态里没有任何正支持，无法与其余证据同时成立，需要复核。'
        else:
            message = '这些观测无法同时对应任何正支持状态，需要复核来源或时间对应关系。'
        conflicts.append({
            'evidence_ids': group,
            'nodes': sorted({item['node'] for item in evidence if item['id'] in involved}),
            'reason': 'no_joint_state_has_positive_support',
            'message': message,
        })
    if limited:
        conflicts.append({
            'evidence_ids': review,
            'nodes': sorted({item['node'] for item in evidence if item['id'] in set(review)}),
            'reason': 'conflict_search_truncated',
            'message': '证据数量超过自动搜索上限；上面只列出在较小证据组合中已确认的矛盾，'
                       '可能还有需要复核的观测，结论不保证完整。',
        })
    return {'supported': False, 'alone': alone, 'conflicts': conflicts, 'review': review,
            'minimal_sets_enumerated': not limited}


def _evidence_factors(evidence):
    factors = {}
    for item in evidence:
        vector = factors.get(item['node'])
        if vector is None:
            vector = [1.0] * len(item['likelihood'])
            factors[item['node']] = vector
        for index, value in enumerate(item['likelihood']):
            vector[index] *= value
    return factors


def _posterior(spec, cpt, factors):
    ordered = spec['ordered']
    nodes = spec['nodes']
    weights = []
    for assignment in spec['assignments']:
        weight = 1.0
        for node_name in ordered:
            node = nodes[node_name]
            key = _row_key(node_name, tuple(assignment[parent] for parent in node['parents']))
            weight *= cpt[key][assignment[node_name]]
            if weight == 0:
                break
        if weight == 0:
            weights.append(0.0)
            continue
        for node_name, vector in factors.items():
            weight *= vector[assignment[node_name]]
            if weight == 0:
                break
        weights.append(weight)
    total = math.fsum(weights)
    if total <= 0:
        return None, 0.0
    posterior = {}
    for node_name in ordered:
        size = len(nodes[node_name]['states'])
        distribution = []
        for state in range(size):
            numerator = math.fsum(weight for weight, assignment in zip(weights, spec['assignments'])
                                  if assignment[node_name] == state)
            distribution.append(numerator / total)
        posterior[node_name] = distribution
    return posterior, total


def completions(spec):
    count = 1
    for _, vertices in spec['rows']:
        count *= len(vertices)
        if count > MAX_COMPLETIONS:
            raise GraphInvalid('条件概率可行组合过多，无法在本地工作台内枚举')
    for choice in itertools.product(*(vertices for _, vertices in spec['rows'])):
        yield {key: vector for (key, _), vector in zip(spec['rows'], choice)}


def _expected_loss(action, distribution):
    return math.fsum(probability * cost for probability, cost in
                     zip(distribution, action['loss_by_damage']))


def _expected_post_test_loss(spec, cpt, posterior, factors, test):
    node_name = test['node']
    distribution = posterior[node_name]
    matrix = test['probabilities']
    width = len(matrix[0])
    expected = 0.0
    for report in range(width):
        report_probability = math.fsum(distribution[state] * matrix[state][report]
                                       for state in range(len(distribution)))
        if report_probability <= 0:
            continue
        updated = {name: list(vector) for name, vector in factors.items()}
        vector = updated.get(node_name)
        if vector is None:
            vector = [1.0] * len(distribution)
            updated[node_name] = vector
        for state in range(len(vector)):
            vector[state] *= matrix[state][report]
        following, total = _posterior(spec, cpt, updated)
        if following is None or total <= 0:
            continue
        best = min(_expected_loss(action, following['damage']) for action in spec['actions'])
        expected += report_probability * best
    return expected


def _estimate_work(spec, budget, evaluate_tests):
    count = 1
    for _, vertices in spec['rows']:
        count *= len(vertices)
    if not evaluate_tests:
        return count * len(spec['assignments'])
    reachable = [test for test in spec['tests']
                 if budget is None or test['cost'] <= budget + TOL]
    width = max((len(test['probabilities'][0]) for test in reachable), default=1)
    return count * len(spec['assignments']) * max(1, len(reachable) * width)


def _evaluate(spec, evidence, budget, evaluate_tests):
    """Posterior bounds and decision/test aggregates over feasible completions."""
    if _estimate_work(spec, budget, evaluate_tests) > MAX_WORK:
        raise GraphInvalid('分析规模超出本地工作台限制，请缩小机理图或证据集合')
    factors = _evidence_factors(evidence)
    bounds_min = {name: [math.inf] * len(spec['nodes'][name]['states'])
                  for name in spec['ordered']}
    bounds_max = {name: [-math.inf] * len(spec['nodes'][name]['states'])
                  for name in spec['ordered']}
    actions = [action['id'] for action in spec['actions']]
    losses = {identifier: [] for identifier in actions}
    tests = [test for test in spec['tests']
             if budget is None or test['cost'] <= budget + TOL] if evaluate_tests else []
    post_test = {test['id']: [] for test in tests}
    test_ids = {test['id'] for test in tests}
    enumerated = 0
    used = 0

    for cpt in completions(spec):
        enumerated += 1
        posterior, total = _posterior(spec, cpt, factors)
        if posterior is None or total <= 0:
            continue
        used += 1
        for node_name in spec['ordered']:
            for state, value in enumerate(posterior[node_name]):
                bounds_min[node_name][state] = min(bounds_min[node_name][state], value)
                bounds_max[node_name][state] = max(bounds_max[node_name][state], value)
        if not spec['actions']:
            continue
        current = {action['id']: _expected_loss(action, posterior['damage'])
                   for action in spec['actions']}
        for identifier, value in current.items():
            losses[identifier].append(value)
        for test in tests:
            post_test[test['id']].append(
                _expected_post_test_loss(spec, cpt, posterior, factors, test))

    if used == 0:
        return None

    bounds = {}
    for node_name in spec['ordered']:
        bounds[node_name] = [[_clean(bounds_min[node_name][state]),
                              _clean(bounds_max[node_name][state])]
                             for state in range(len(spec['nodes'][node_name]['states']))]

    decision = None
    selected = None
    if spec['actions']:
        expected = {action['id']: [_clean(min(losses[action['id']])),
                                   _clean(max(losses[action['id']]))] for action in spec['actions']}
        worst = {identifier: expected[identifier][1] for identifier in actions}
        selected = min(actions, key=lambda identifier: (worst[identifier], actions.index(identifier)))
        others = [identifier for identifier in actions if identifier != selected]
        runner_up = min((worst[identifier] for identifier in others), default=None)
        decision = {
            'criterion': 'minimax_expected_loss_over_feasible_cpt_completions',
            'action': selected,
            'expected_loss_bounds': expected,
            'worst_case_loss': worst[selected],
            'margin_over_next_worst_case': None if runner_up is None else _clean(
                runner_up - worst[selected]),
            'uniquely_optimal': None if runner_up is None
            else runner_up - worst[selected] > TOL,
            'interpretation': ('在可行条件概率集合上，取最坏情形期望损失最小的处置动作；'
                               '这是成本决策，不是责任或因果效应判断。'),
        }

    test_value = None
    if evaluate_tests:
        evaluated = []
        unavailable = []
        for test in spec['tests']:
            if test['id'] not in test_ids:
                unavailable.append({'id': test['id'], 'node': test['node'],
                                    'cost': _clean(test['cost']), 'reason': 'over_budget'})
                continue
            if not spec['actions']:
                unavailable.append({'id': test['id'], 'node': test['node'],
                                    'cost': _clean(test['cost']), 'reason': 'no_decision_actions'})
                continue
            # Expected loss of the action this analysis would actually take,
            # versus waiting for the test result and then choosing again.
            reductions = [losses[selected][index] - post for index, post in
                          enumerate(post_test[test['id']])]
            if not reductions:
                continue
            low, high = min(reductions), max(reductions)
            evaluated.append({
                'id': test['id'],
                'node': test['node'],
                'cost': _clean(test['cost']),
                'within_budget': True,
                'report_states': test['report_states'],
                'decision_loss_reduction_range': [_clean(low), _clean(high)],
                'net_value_range': [_clean(low - test['cost']), _clean(high - test['cost'])],
                'min_net_value_over_completions': _clean(low - test['cost']),
                'basis': ('对每个可行条件概率完成，先取本次分析建议的处置在该完成下的期望损失，'
                          '减去等待该补验结果后再选最优处置的期望损失，再减去补验成本；'
                          '区间是可行完成之间的范围，不是参数后验。补验报告被视为在节点状态'
                          '给定后与既有证据条件独立。'),
            })
        evaluated.sort(key=lambda row: (-row['min_net_value_over_completions'], row['cost'], row['id']))
        for rank, row in enumerate(evaluated, 1):
            row['rank'] = rank
        recommended = next((row['id'] for row in evaluated
                            if row['min_net_value_over_completions'] > TOL), None)
        test_value = {
            'criterion': 'decision_loss_reduction_minus_test_cost',
            'baseline': None if decision is None else {
                'action': decision['action'],
                'expected_loss_bounds': decision['expected_loss_bounds'],
            },
            'budget': None if budget is None else _clean(budget),
            'cost_unit': '与处置损失相同的每批成本单位',
            'tests': evaluated,
            'unavailable_tests': unavailable,
            'recommended_test': recommended,
            'ranking_note': ('按可行完成范围内净价值的最小值排序；该最小值是在枚举出的顶点完成上取得的，'
                             '不构成对全部可行参数的下界证明。'),
            'recommendation_note': (
                '仅当枚举完成上的最小净价值为正才列为推荐；预算按单项补验成本检查，'
                '多项补验的信息相关性与组合成本未建模，不把单项价值相加。'
                if recommended else
                '没有在预算内且枚举完成上最小净价值为正的补验。'),
        }

    return {
        'posterior': bounds,
        'decision': decision,
        'test_value': test_value,
        'completions_enumerated': enumerated,
        'completions_used': used,
    }


def _parse_exclusions(case, exclude_evidence):
    if exclude_evidence is None:
        return []
    if not isinstance(exclude_evidence, list) or any(not isinstance(value, str)
                                                     for value in exclude_evidence):
        raise ValueError('exclude_evidence 必须是证据标识列表')
    known = {row['id'] for row in case['evidence']}
    unknown = [value for value in exclude_evidence if value not in known]
    if unknown:
        raise ValueError('未知证据标识：' + ', '.join(sorted(unknown)))
    ordered = []
    for value in exclude_evidence:
        if value not in ordered:
            ordered.append(value)
    return ordered


def _parse_budget(case, budget):
    if budget is None:
        budget = case.get('budget')
    if budget is None:
        return None
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) \
            or not math.isfinite(budget) or budget < 0:
        raise ValueError('budget 必须是非负有限数值')
    return float(budget)


def _interpretation_limits():
    return {
        'conditional_inference_only': True,
        'not_liability_finding': True,
        'not_causal_effect_estimate': True,
        'statement': ('后验描述的是在机理图和观测似然假设下各状态与当前证据的相容程度；'
                      '某个原因在观测后更可能，不等于证明该原因造成了损失，'
                      '也不能解读为干预效果或责任认定。'),
        'evidence_dependence': ('证据似然按图节点条件相乘；共享上游原因（例如同一段受热）'
                                '会让温度记录与到货外观相关，不能把它们当作两张独立选票，'
                                '也不能把条件概率相乘当作独立证据数。'),
        'interval_meaning': ('条件概率区间表示知识不确定，而不是随机参数；后验界限是可行参数集合上的界限，'
                             '不同节点的界限不保证由同一个参数完成同时达到，也不保证逐状态相加为一。'),
    }


def _evidence_sources(case, excluded):
    sources = []
    rows = case.get('evidence') if isinstance(case, dict) else None
    if not isinstance(rows, list):
        return sources
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {
            'id': row.get('id'),
            'node': row.get('node'),
            'likelihood': row.get('likelihood'),
            'status': 'excluded' if row.get('id') in excluded else 'included',
        }
        if 'source' in row:
            item['source'] = row['source']
        sources.append(item)
    return sources


def _exclusion_diagnostics(evidence, excluded, baseline, result):
    change = {
        'excluded_evidence': excluded,
        'remaining_evidence': [row.get('id') for row in evidence if row.get('id') not in excluded],
        'baseline_status': None if baseline is None else baseline['status'],
        'current_status': 'compatible' if result is not None else 'incompatible',
        'decision_before': None if baseline is None else baseline.get('action'),
        'decision_after': None if result is None or result.get('decision') is None
        else result['decision']['action'],
    }
    if baseline is not None and baseline['status'] == 'compatible' and result is not None:
        change['decision_changed'] = change['decision_before'] != change['decision_after']
        shifts = {}
        previous_all = baseline.get('posterior') or {}
        for node_name, current in result['posterior'].items():
            previous = previous_all.get(node_name)
            if previous is None:
                continue
            shifts[node_name] = _clean(max(
                max(abs(current[state][0] - previous[state][0]),
                    abs(current[state][1] - previous[state][1]))
                for state in range(len(current))))
        change['posterior_max_abs_change'] = shifts
        change['posterior_before'] = previous_all
    else:
        # The comparison is still reported even when one side has no usable
        # posterior (for example the full evidence was already contradictory).
        change['decision_changed'] = None
        change['posterior_before'] = None if baseline is None else baseline.get('posterior')
        change['posterior_after'] = None if result is None else result.get('posterior')
    change['note'] = ('这是撤除观测后的敏感性对照，用来说明结论为何变化；'
                      '判断依赖机理图与观测似然假设，不是因果或责任判断。')
    return change


def _diagnostics(spec, case, excluded, support, result=None, baseline=None, graph_error=None):
    rows = case.get('evidence') if isinstance(case, dict) else None
    evidence = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    included = [row for row in evidence if row.get('id') not in excluded]
    diagnostics = {
        'graph_version': case.get('graph_version') if isinstance(case, dict) else None,
        'analysis_kind': 'conditional_evidence_update',
        'evidence_sources': _evidence_sources(case if isinstance(case, dict) else {}, excluded),
        'parameter_uncertainty': None,
        'decision_basis': None,
        'information_limits': _interpretation_limits(),
        'warnings': [],
    }
    nodes_used = [row.get('node') for row in included]
    if len(nodes_used) != len(set(nodes_used)):
        diagnostics['warnings'].append(
            '同一节点上有多条证据记录；按节点条件相乘处理。若它们实际来自同一传感来源，'
            '会高估独立信息量，应先复核来源并在资料中用 source 标明。')
    if graph_error is not None:
        diagnostics['graph_error'] = graph_error
        return diagnostics
    diagnostics['support_check'] = {
        'status': 'supported' if support['supported'] else 'zero_support',
        'evidence_alone': support['alone'],
        'review_evidence': support['review'],
        'minimal_sets_enumerated': support.get('minimal_sets_enumerated', True),
    }
    if not support['supported']:
        diagnostics['conflicts'] = support['conflicts']
        diagnostics['review_evidence'] = support['review']
        diagnostics['parameter_uncertainty'] = {
            'representation': '每行独立的 [lower, upper] + 行和为一约束',
            'note': '零支持时不计算后验，也不把概率重新归一成一个看似正常的结论。',
        }
        if excluded:
            diagnostics['evidence_exclusion'] = _exclusion_diagnostics(
                evidence, excluded, baseline, None)
        return diagnostics

    diagnostics['parameter_uncertainty'] = {
        'representation': '每行独立的 [lower, upper] + 行和为一约束；条件概率行之间独立',
        'completions_evaluated': result['completions_used'],
        'completions_enumerated': result['completions_enumerated'],
        'posterior_bound_method': ('枚举各行可行多面体的顶点并逐个完成精确更新；节点后验界限取所有可行完成'
                                   '上的极值，因此是参数集合上的严格界限，不是抽样近似。'),
        'decision_bound_method': '处置期望损失的极值同样来自这些可行完成；决策采用最坏情形期望损失最小。',
        'test_value_range_method': ('补验价值在每个可行完成上分别计算，报告完成之间的范围；'
                                    '排序使用范围下端，不声称是参数不确定性的严格全局包络。'),
    }
    decision = result.get('decision')
    diagnostics['decision_basis'] = None if decision is None else {
        'criterion': decision['criterion'],
        'action': decision['action'],
        'expected_loss_bounds': decision['expected_loss_bounds'],
        'worst_case_loss': decision['worst_case_loss'],
        'margin_over_next_worst_case': decision['margin_over_next_worst_case'],
        'uniquely_optimal': decision['uniquely_optimal'],
    }
    if excluded:
        diagnostics['evidence_exclusion'] = _exclusion_diagnostics(
            evidence, excluded, baseline, result)
    return diagnostics


def _compatibility(status, reason, message, support):
    return {
        'status': status,
        'reason': reason,
        'message': message,
        'review_evidence': support['review'],
        'conflicts': support['conflicts'],
    }


def _baseline(spec):
    """Full-evidence result used only as the sensitivity comparison."""
    support = support_analysis(spec, spec['evidence'])
    if not support['supported']:
        return {'status': 'incompatible', 'posterior': None, 'action': None}
    try:
        full = _evaluate(spec, spec['evidence'], None, evaluate_tests=False)
    except GraphInvalid:
        return {'status': 'incompatible', 'posterior': None, 'action': None}
    if full is None:
        return {'status': 'incompatible', 'posterior': None, 'action': None}
    return {
        'status': 'compatible',
        'posterior': full['posterior'],
        'action': None if full['decision'] is None else full['decision']['action'],
    }


def analyze(case, exclude_evidence=None, budget=None):
    """Return the /evidence-diagnosis payload for one study case."""
    snapshot = case.get('_snapshot') if isinstance(case, dict) else None
    try:
        spec = validate_case(case)
        excluded = _parse_exclusions(case, exclude_evidence)
        effective_budget = _parse_budget(case, budget)
    except GraphInvalid as error:
        excluded = exclude_evidence if isinstance(exclude_evidence, list) else []
        support = {'supported': False, 'alone': [], 'conflicts': [], 'review': []}
        return {
            'snapshot': snapshot,
            'posterior': None,
            'compatibility': _compatibility('incompatible', 'graph_invalid', str(error), support),
            'test_value': None,
            'diagnostics': _diagnostics(None, case, excluded, support, graph_error=str(error)),
        }

    baseline = _baseline(spec) if excluded else None
    included = [row for row in spec['evidence'] if row['id'] not in excluded]
    support = support_analysis(spec, included)
    if not support['supported']:
        return {
            'snapshot': snapshot,
            'posterior': None,
            'compatibility': _compatibility(
                'incompatible', 'zero_support',
                '联合证据在可行机理参数和状态上没有正支持；不输出归一化后验。', support),
            'test_value': None,
            'diagnostics': _diagnostics(spec, case, excluded, support, baseline=baseline),
        }

    try:
        result = _evaluate(spec, included, effective_budget, evaluate_tests=True)
    except GraphInvalid as error:
        return {
            'snapshot': snapshot,
            'posterior': None,
            'compatibility': _compatibility('incompatible', 'graph_invalid', str(error), support),
            'test_value': None,
            'diagnostics': _diagnostics(spec, case, excluded, support, baseline=baseline,
                                        graph_error=str(error)),
        }
    if result is None:
        # Support analysis passed but every completion had zero evidence mass.
        # Keep the non-normalizing contract instead of inventing a posterior.
        support = {'supported': False, 'alone': support['alone'], 'review': [
            row['id'] for row in included], 'conflicts': [{
                'evidence_ids': [row['id'] for row in included],
                'nodes': sorted({row['node'] for row in included}),
                'reason': 'no_completion_has_positive_evidence_mass',
                'message': '所有可行参数完成下联合证据概率为零，需要复核证据。',
            }]}
        return {
            'snapshot': snapshot,
            'posterior': None,
            'compatibility': _compatibility(
                'incompatible', 'zero_support',
                '联合证据在可行机理参数和状态上没有正支持；不输出归一化后验。', support),
            'test_value': None,
            'diagnostics': _diagnostics(spec, case, excluded, support, baseline=baseline),
        }

    return {
        'snapshot': snapshot,
        'posterior': result['posterior'],
        'compatibility': _compatibility(
            'compatible', None, '存在与全部证据正支持的机理状态。', support),
        'test_value': result['test_value'],
        'diagnostics': _diagnostics(spec, case, excluded, support, result=result, baseline=baseline),
    }
