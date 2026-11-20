"""데모 계정 만들기 (B 명세 7.1 페르소나 3명) + 공통 프로필(PROFILE#BASIC) 채우기.

실행 (aws login 후):
  uv run --python 3.13 --with boto3 --with "botocore[crt]" infra/seed_demo.py

- 비밀번호는 무작위로 만들어 Secrets Manager `team07/demo-accounts`에만 저장한다.
  저장소(공개)·화면·로그에 출력하지 않는다. 확인은 AWS 콘솔 → Secrets Manager.
- 여러 번 실행해도 안전하다. 이미 있는 계정은 비밀번호를 바꾸지 않고 프로필만 갱신한다.
"""

import json
import secrets
import string
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

REGION = "ap-northeast-2"
POOL_NAME = "team07-users"
SECRET_NAME = "team07/demo-accounts"
TABLE = "team07-career-mentor"
NOW = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")

# B 개발명세서 7.1 페르소나. 시군구는 법정동 코드 (부산 26)
PERSONAS = {
    "demo1": {"label": "① 서울 저울질형", "birthYear": 2003, "residenceSido": "26", "residenceSigungu": "26290",
              "universityRegion": "26", "graduationStatus": "GRADUATING", "educationLevel": "BACHELOR", "major": "통계학",
              "desiredJobs": [{"work24Code": None, "ncsCode": "20010105", "name": "데이터 분석"}],
              "employmentStatus": "UNEMPLOYED", "priorities": ["SALARY", "GROWTH"], "desiredRegion": "ALL"},
    "demo2": {"label": "② 남고 싶은데 막막형", "birthYear": 1999, "residenceSido": "26", "residenceSigungu": "26380",
              "universityRegion": "26", "graduationStatus": "GRADUATED", "educationLevel": "ASSOCIATE", "major": "경영학",
              "desiredJobs": [{"work24Code": None, "ncsCode": "02030201", "name": "사무·회계"}],
              "employmentStatus": "UNEMPLOYED", "priorities": ["STABILITY", "WORK_LIFE"], "desiredRegion": "26"},
    "demo3": {"label": "③ 공기업 준비형", "birthYear": 2001, "residenceSido": "26", "residenceSigungu": "26410",
              "universityRegion": "26", "graduationStatus": "GRADUATING", "educationLevel": "BACHELOR", "major": "경제학",
              "desiredJobs": [{"work24Code": None, "ncsCode": None, "name": "공공기관 금융·행정"}],
              "employmentStatus": "UNEMPLOYED", "priorities": ["STABILITY"], "desiredRegion": "26"},
}


def new_password():
    # 사용자 풀 정책: 8자 이상, 소문자·숫자 포함
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(16))
        if any(c.islower() for c in pw) and any(c.isdigit() for c in pw):
            return pw


def main():
    idp = boto3.client("cognito-idp", region_name=REGION)
    sm = boto3.client("secretsmanager", region_name=REGION)
    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)

    pool_id = next(p["Id"] for p in idp.list_user_pools(MaxResults=60)["UserPools"] if p["Name"] == POOL_NAME)
    try:
        stored = json.loads(sm.get_secret_value(SecretId=SECRET_NAME)["SecretString"])
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        stored = {}

    for username, persona in PERSONAS.items():
        try:
            user = idp.admin_get_user(UserPoolId=pool_id, Username=username)
            created = False
        except idp.exceptions.UserNotFoundException:
            idp.admin_create_user(UserPoolId=pool_id, Username=username, MessageAction="SUPPRESS")
            user, created = None, True
        if created or username not in stored:
            stored[username] = {"password": new_password(), "persona": persona["label"]}
            idp.admin_set_user_password(UserPoolId=pool_id, Username=username, Password=stored[username]["password"], Permanent=True)
        user = user or idp.admin_get_user(UserPoolId=pool_id, Username=username)
        sub = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")

        profile = {k: v for k, v in persona.items() if k != "label"}
        table.put_item(Item={"PK": f"USER#{sub}", "SK": "PROFILE#BASIC", "entityType": "BasicProfile", "schemaVersion": "1.0",
                             "ownerUserId": sub, **profile, "talentPoolConsent": False, "isDemo": True,
                             "createdAt": NOW, "updatedAt": NOW})
        print(f"{'+' if created else '='} {username} {persona['label']} — 프로필 저장")

    payload = json.dumps(stored, ensure_ascii=False)
    try:
        sm.put_secret_value(SecretId=SECRET_NAME, SecretString=payload)
    except sm.exceptions.ResourceNotFoundException:
        sm.create_secret(Name=SECRET_NAME, SecretString=payload, Tags=[{"Key": "team", "Value": "team07"}],
                         Description="7팀 데모 계정 비밀번호 (저장소에 적지 않음)")
    print(f"비밀번호: Secrets Manager '{SECRET_NAME}'에 저장 (출력하지 않음)")


if __name__ == "__main__":
    main()
