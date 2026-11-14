import math


def rows_by_id(rows):
    result = {}
    for row in rows:
        if row['id'] in result:
            raise ValueError('重复标识：' + row['id'])
        result[row['id']] = row
    return result


def positive_integer(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError('需要正整数')
    return value


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('概率必须是零到一的有限数值')
    return value
