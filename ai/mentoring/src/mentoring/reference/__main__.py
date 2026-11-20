"""기본 dry-run인 NCS reference 적재 명령."""

from __future__ import annotations

import argparse
import json
import os

from .loader import ReferenceLoader


def main() -> int:
    parser = argparse.ArgumentParser(description="NCS structured CSV 적재 계획을 확인하거나 실행합니다.")
    parser.add_argument("--source", required=True, help="structured CSV 5개가 있는 폴더")
    parser.add_argument("--write", action="store_true", help="명시하면 DynamoDB에 멱등 적재")
    args = parser.parse_args()

    loader = ReferenceLoader(args.source)
    table = None
    if args.write:
        table_name = os.environ.get("TABLE_REFERENCE")
        if not table_name:
            parser.error("--write에는 TABLE_REFERENCE 환경변수가 필요합니다.")
        import boto3

        table = boto3.resource("dynamodb").Table(table_name)
    report = loader.load(table, write=args.write)
    print(json.dumps(report.model_dump(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
