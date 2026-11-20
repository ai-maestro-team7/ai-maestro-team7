"""Collect official exam calendars and NCS reference data for the mentoring catalog."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.parse import unquote, urlencode
from urllib.request import urlopen

from .ncs_workbook import collect_workbook

EXAM_URL = "https://apis.data.go.kr/B490007/qualExamSchd/getQualExamSchdList"
KST = timezone(timedelta(hours=9))


def catalog_codes(table, prefix, sort_key):
    params = {"ProjectionExpression": "PK, SK", "FilterExpression": "begins_with(PK, :p) AND SK = :s",
              "ExpressionAttributeValues": {":p": prefix, ":s": sort_key}}
    codes = set()
    while True:
        page = table.scan(**params)
        codes.update(row["PK"].removeprefix(prefix) for row in page["Items"])
        if not page.get("LastEvaluatedKey"):
            break
        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    if not codes:
        raise ValueError("멘토링 기준 테이블에 수집 대상이 없습니다")
    return sorted(codes)


def save_snapshot(table, item):
    from botocore.exceptions import ClientError

    # A slower, overlapping invocation cannot replace a more recent snapshot.
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(collectedAt) OR collectedAt <= :at",
                       ExpressionAttributeValues={":at": item["collectedAt"]})
    except ClientError as error:
        if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise


def exam_page(key, code, year, page):
    params = {"serviceKey": key, "jmCd": code, "implYy": year, "dataFormat": "json",
              "pageNo": page, "numOfRows": 50}
    try:
        with urlopen(f"{EXAM_URL}?{urlencode(params)}", timeout=20) as response:
            payload = json.load(response)
    except (URLError, TimeoutError, ValueError):
        # HTTP exceptions can contain a service key in the request URL.
        raise RuntimeError("시험일정 API 호출 실패") from None
    if payload.get("header", {}).get("resultCode") != "00":
        raise RuntimeError("시험일정 API 오류 응답")
    return payload["body"]


def exam_rows(key, code, year):
    rows = []
    page = 1
    expected = None
    while True:
        body = exam_page(key, code, year, page)
        total = int(body["totalCount"])
        if expected is not None and total != expected:
            raise ValueError("시험일정 페이지 조회 중 총 건수가 변경됐습니다")
        expected = total
        items = body.get("items") or []
        if not isinstance(items, list) or any(str(row.get("implYy")) != str(year) for row in items):
            raise ValueError("시험일정 응답 형식 또는 시행 연도가 다릅니다")
        if int(body["pageNo"]) != page or len(rows) + len(items) > total:
            raise ValueError("시험일정 페이지가 일치하지 않습니다")
        rows.extend(items)
        if len(rows) == total:
            return rows
        if not items:
            raise ValueError("시험일정 페이지 일부가 누락됐습니다")
        page += 1


def collect(source):
    import boto3

    now = datetime.now(KST)
    db = boto3.resource("dynamodb")
    reference = db.Table(os.environ["TABLE_REFERENCE"])
    if source == "ncs":
        codes = catalog_codes(reference, "NCS#", "PROFILE")
        return collect_workbook(reference, codes, now, save_snapshot)
    if source != "exams":
        raise ValueError("지원하지 않는 멘토링 수집 이벤트")
    codes = catalog_codes(reference, "QUAL#", "META")
    secret = boto3.client("secretsmanager").get_secret_value(SecretId=os.environ["OPP_SECRET_ID"])
    keys = json.loads(secret["SecretString"])
    key = unquote(keys.get("DATA_GO_KR_SERVICE_KEY") or keys["DATA_GO_KR_KEY"])
    cache = db.Table(os.environ["TABLE_CACHE"])
    count = 0
    for code in codes:
        for year in (now.year, now.year + 1):
            rows = exam_rows(key, code, year)
            digest = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            save_snapshot(cache, {
                "cache_key": f"EXAM#{code}#{year}", "qualificationCode": code, "year": year,
                "items": rows, "sourceUrl": EXAM_URL, "collectedAt": now.isoformat(),
                "sha256": digest, "expires_at": int((now + timedelta(days=1)).timestamp()),
            })
            count += len(rows)
    return {"source": source, "qualifications": len(codes), "schedules": count}
