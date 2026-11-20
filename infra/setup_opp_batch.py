#!/usr/bin/env python3
"""B 개발계획서 §2.1·§3.1 / #83: 기존 Lambda 설정을 보존하며 정기 수집을 연결한다.

코드 배포와 setup-role.sh 적용 후 실행: python3 infra/setup_opp_batch.py
--disabled: 시연 중 두 정기 일정만 중지한다. 사용자별 일회성 알림은 건드리지 않는다.
AWS CLI를 사용하므로 aws login 자격 증명을 그대로 쓴다. 환경변수 값은 출력하지 않는다.
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

REGION = "ap-northeast-2"
FUNCTION = "team07-api"
SECRET = "team07/opp-api-keys"
TIMEOUT = 900
SCHEDULES = (
    ("team07-opp-daily-ingest", "cron(30 4 * * ? *)", {"step": "ingest"}),
    ("team07-opp-weekly-companies", "cron(0 5 ? * MON *)", {"step": "ingest", "frequency": "weekly"}),
)


class AwsError(RuntimeError):
    def __init__(self, service, action, *, not_found=False):
        super().__init__(f"AWS {service} {action} 실패: 로그인·리전·권한을 확인하세요")
        self.not_found = not_found


def aws(service, action, *args):
    result = subprocess.run(
        ["aws", "--region", REGION, "--output", "json", "--no-cli-pager", service, action, *args],
        capture_output=True, text=True,
    )
    if result.returncode:
        # stderr에는 환경변수나 URL이 섞일 수 있어 그대로 출력하지 않는다.
        raise AwsError(service, action, not_found="ResourceNotFoundException" in result.stderr)
    return json.loads(result.stdout) if result.stdout.strip() else {}


def set_lambda_config(current):
    variables = dict(current.get("Environment", {}).get("Variables", {}))
    variables.setdefault("OPP_SECRET_ID", SECRET)
    # 기존 설정은 전부 보존한다. 필요한 값이 없으면 일정을 활성화하지 않는다.
    required = (
        "TABLE_CATALOG", "TABLE_CAREER_MENTOR", "OPP_DATA_BUCKET",
        "OPP_VECTOR_BUCKET", "OPP_VECTOR_INDEX", "MODEL_ID", "EMBEDDING_MODEL_ID",
        "SCHEDULER_TARGET_ARN", "SCHEDULER_ROLE_ARN",
    )
    missing = [name for name in required if not variables.get(name)]
    if missing:
        raise RuntimeError("Lambda 필수 설정 누락: " + ", ".join(missing))
    aws("secretsmanager", "describe-secret", "--secret-id", variables["OPP_SECRET_ID"])
    if variables != current.get("Environment", {}).get("Variables", {}) or current["Timeout"] != TIMEOUT:
        with tempfile.TemporaryDirectory(prefix="team07-opp-") as tmp:
            path = Path(tmp) / "environment.json"
            path.write_text(json.dumps({"Variables": variables}), encoding="utf-8")
            path.chmod(0o600)
            aws(
                "lambda", "update-function-configuration", "--function-name", FUNCTION,
                "--environment", f"file://{path}", "--timeout", str(TIMEOUT),
                "--revision-id", current["RevisionId"],
            )
        aws("lambda", "wait", "function-updated", "--function-name", FUNCTION)
    return variables


def put_schedule(name, expression, event, function_arn, role_arn, *, disabled):
    spec = {
        "Name": name, "GroupName": "default",
        "Description": "team07 부산 기회 추천 정기 수집",
        "ScheduleExpression": expression, "ScheduleExpressionTimezone": "Asia/Seoul",
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "State": "DISABLED" if disabled else "ENABLED",
        "Target": {
            "Arn": function_arn, "RoleArn": role_arn,
            "Input": json.dumps({"oppBatch": event}, separators=(",", ":")),
            # 전송 실패는 두 번 재시도하되 한 시간 넘게 지연된 실행은 시작하지 않는다.
            "RetryPolicy": {"MaximumEventAgeInSeconds": 3600, "MaximumRetryAttempts": 2},
        },
    }
    try:
        aws("scheduler", "get-schedule", "--name", name, "--group-name", "default")
    except AwsError as error:
        if not error.not_found:
            raise
        action = "create-schedule"
    else:
        action = "update-schedule"
    with tempfile.TemporaryDirectory(prefix="team07-opp-") as tmp:
        path = Path(tmp) / "schedule.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        aws("scheduler", action, "--cli-input-json", f"file://{path}")
    print(f"{name}: {spec['State']} / {expression} / Asia/Seoul")


def configure(*, disabled=False):
    current = aws("lambda", "get-function-configuration", "--function-name", FUNCTION)
    if current.get("LastUpdateStatus") == "InProgress":
        aws("lambda", "wait", "function-updated", "--function-name", FUNCTION)
        current = aws("lambda", "get-function-configuration", "--function-name", FUNCTION)
    if current.get("LastUpdateStatus") == "Failed":
        raise RuntimeError("Lambda의 직전 설정 갱신이 실패했습니다")
    function_arn = current["FunctionArn"]
    if function_arn.split(":")[3] != REGION or function_arn.split(":")[-1] != FUNCTION:
        raise RuntimeError("team07-api 함수·리전이 아닙니다")
    account = function_arn.split(":")[4]
    role_arn = f"arn:aws:iam::{account}:role/team07-scheduler-role"
    aws("iam", "get-role", "--role-name", "team07-scheduler-role")
    if not disabled:
        variables = current.get("Environment", {}).get("Variables", {})
        if variables.get("SCHEDULER_TARGET_ARN") != function_arn or variables.get("SCHEDULER_ROLE_ARN") != role_arn:
            raise RuntimeError("기존 B 일정 대상·역할이 team07-api 설정과 다릅니다")
        set_lambda_config(current)
    for name, expression, event in SCHEDULES:
        put_schedule(name, expression, event, function_arn, role_arn, disabled=disabled)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disabled", action="store_true")
    args = parser.parse_args()
    try:
        configure(disabled=args.disabled)
    except (AwsError, RuntimeError, FileNotFoundError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
