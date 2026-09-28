"""Private text-only regex subprocess protocol; never executes user code."""
import json
import re
import sys


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    request = json.loads(sys.stdin.readline())
    try:
        pattern = re.compile(request['pattern'], 0 if request['case_sensitive'] else re.IGNORECASE)
    except (re.error, OverflowError, ValueError, RecursionError) as error:
        emit({'error': str(error)})
        return
    emit({'ready': True})
    for raw in sys.stdin:
        request = json.loads(raw)
        matches = []
        for number, line in enumerate(request['text'].splitlines(), 1):
            if pattern.search(line):
                matches.append({'line': number, 'text': line[:1000]})
            if len(matches) >= request['max_matches']:
                break
        emit({'matches': matches})


if __name__ == '__main__':
    main()
