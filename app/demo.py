import json
import threading

from app.client import analysis, request
from app.server import make_server


def main():
    with make_server() as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        print(json.dumps(request(base, '/health'), ensure_ascii=False))
        for case in request(base, '/cases')['cases']:
            response = request(base, '/preview', {'case': case})
            print(json.dumps({'case': case, 'preview': response}, ensure_ascii=False))
        for case in request(base, '/study-cases')['cases']:
            response = request(base, '/study-preview', {'case': case})
            print(json.dumps({'study': case, 'preview': response}, ensure_ascii=False))
        for case in request(base, '/study-cases')['cases']:
            response = analysis(base, case)
            print(json.dumps({'study': case, 'diagnosis': response}, ensure_ascii=False))
        # Sensitivity: drop one observation and show what changed and why.
        sensitivity = analysis(base, 'edge', exclude_evidence=['conflict'])
        print(json.dumps({'study': 'edge', 'exclude_evidence': ['conflict'],
                          'diagnosis': sensitivity}, ensure_ascii=False))
        # Sensitivity on a compatible case: the same comparison without a
        # status change, to show the posterior shift.
        shifted = analysis(base, 'interval', exclude_evidence=['sensor'])
        print(json.dumps({'study': 'interval', 'exclude_evidence': ['sensor'],
                          'diagnosis': shifted}, ensure_ascii=False))
        # Budget: the same case with a budget that rules out every test.
        tight = analysis(base, 'interval', budget=0.2)
        print(json.dumps({'study': 'interval', 'budget': 0.2, 'test_value': tight['test_value']},
                         ensure_ascii=False))
        server.shutdown()
        worker.join(timeout=3)


if __name__ == '__main__':
    main()
