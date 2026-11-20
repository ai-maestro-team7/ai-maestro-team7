"""부산 기업 둘러보기 REST 경로."""

import json

from opportunity.api import rest_handler
from opportunity.models import Badge, CompanyRecord

BASE = "/api/v1/opportunities"


def call(deps, path, query=None, user="demo1"):
    event = {"version": "2.0", "routeKey": "$default", "rawPath": BASE + path, "rawQueryString": "",
             "queryStringParameters": query, "headers": {"content-type": "application/json"}, "isBase64Encoded": False,
             "requestContext": {"requestId": "req-test", "stage": "$default",
                                "http": {"method": "GET", "path": BASE + path, "protocol": "HTTP/1.1",
                                         "sourceIp": "127.0.0.1", "userAgent": "pytest"}}}
    response = rest_handler.handle(event, deps, user)
    return response["statusCode"], json.loads(response["body"])


def cheonggeul(deps, cid, name, kind, label, industry):
    badge = Badge(type="CHEONGKKEUL", label=label, cheonggeul_type=kind, source="부산광역시 (테스트)", as_of="2026-03-26")
    deps.catalog.put_company(CompanyRecord(company_id=cid, name=name, sido="26", industry=industry, highlights=[badge],
                                           district="해운대구", source="부산광역시 (테스트)", as_of="2026-03-26"))


def test_companies_route_returns_cards_without_hiring_claims(deps):
    cheonggeul(deps, "name-t1", "(주)테스트데이터", "SALARY", "청끌기업 · 급여", "데이터 분석 소프트웨어 개발업")
    cheonggeul(deps, "name-t2", "(주)테스트조선", "WORK_LIFE", "청끌기업 · 워라밸", "선박 부분품 제조업")
    status, body = call(deps, "/companies")
    assert status == 200 and body["basis"] and body["notice"]
    names = [c["name"] for c in body["items"]]
    assert "(주)테스트데이터" in names and "(주)테스트조선" in names
    assert "채용 중" not in json.dumps(body["items"], ensure_ascii=False)  # 카드에는 채용 여부를 적지 않는다
    status, body = call(deps, "/companies", {"category": "WORK_LIFE", "limit": "1"})
    assert status == 200 and len(body["items"]) == 1 and body["items"][0]["badges"][0]["cheonggeulType"] == "WORK_LIFE"


def test_companies_route_rejects_bad_category(deps):
    status, body = call(deps, "/companies", {"category": "NOPE"})
    assert status == 400 and body["error"]["code"] == "INVALID_INPUT"
