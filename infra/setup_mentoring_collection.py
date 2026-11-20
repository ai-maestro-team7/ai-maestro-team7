"""Enable the mentoring schedules on the existing API Lambda in Seoul."""
import json
import tempfile
from pathlib import Path

from setup_opp_batch import FUNCTION, aws, put_schedule


def configure():
    current = aws("lambda", "get-function-configuration", "--function-name", FUNCTION)
    variables = current["Environment"]["Variables"].copy()
    target = current["FunctionArn"]
    role = variables["SCHEDULER_ROLE_ARN"]
    if target != variables["SCHEDULER_TARGET_ARN"] or not variables.get("OPP_SECRET_ID"):
        raise ValueError("기존 스케줄러 대상과 API 비밀 설정을 확인하세요")
    if current["Timeout"] < 900:
        raise ValueError("공식 NCS 원장 수집에는 기존 900초 Lambda 설정이 필요합니다")
    for key, table in (("TABLE_REFERENCE", "team07-reference"), ("TABLE_CACHE", "team07-cache")):
        aws("dynamodb", "describe-table", "--table-name", variables.setdefault(key, table))
    if variables != current["Environment"]["Variables"]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "environment.json"
            path.write_text(json.dumps({"Variables": variables}))
            aws("lambda", "update-function-configuration", "--function-name", FUNCTION,
                "--environment", f"file://{path}", "--revision-id", current["RevisionId"])
        aws("lambda", "wait", "function-updated", "--function-name", FUNCTION)
    for source, expression in (("exams", "cron(0 6 * * ? *)"), ("ncs", "cron(0 7 ? * TUE *)")):
        put_schedule(f"team07-mentoring-{source}", expression, source, target, role,
                     disabled=False, event_key="mentoringCollection", description="team07 멘토링 공식 자료 수집")


if __name__ == "__main__":
    configure()
