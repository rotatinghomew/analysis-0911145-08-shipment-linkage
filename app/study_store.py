import hashlib
import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'data' / 'study'


def names():
    return sorted(path.stem for path in DATA.glob('*.json'))


def load_case(name):
    if name not in names():
        raise ValueError('未知分析资料')
    raw = (DATA / (name + '.json')).read_bytes()
    case = json.loads(raw)
    case['_snapshot'] = hashlib.sha256(raw).hexdigest()
    return case
