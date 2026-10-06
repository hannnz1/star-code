"""Validate a reference deployment; never deploy an unverified image manifest."""
import argparse
import json
from pathlib import Path

from muse.commerce.environment import environment_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--environment', choices=['staging', 'live-test'], required=True)
    parser.add_argument('--lock', type=Path, default=Path('deploy/commerce/versions.lock.json'))
    args = parser.parse_args()
    try:
        config = environment_config(args.project, args.environment, json.loads(args.lock.read_text(encoding='utf-8')))
    except (ValueError, OSError):
        parser.exit(2, 'Reference environment is not verified; see docs/commerce/environment.md\n')
    print(json.dumps(config, indent=2))


if __name__ == '__main__':
    main()
