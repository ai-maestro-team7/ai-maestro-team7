"""EventBridge Scheduler 구현. 일회성 `at()` 일정을 Asia/Seoul 기준으로 만들고, 실행이 끝나면 자동으로 지운다."""

import json
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError

from ..core import clock
from ..models.errors import aws_service_error
from .dynamo import error_code

SERVICE = "scheduler"
TIMEZONE = "Asia/Seoul"


class EventBridgeScheduler:
    """target_arn은 일정이 울릴 때 부를 Lambda, role_arn은 Scheduler가 그 Lambda를 부를 때 쓰는 역할이다."""

    def __init__(self, client, *, target_arn: str, role_arn: str, group_name: str | None = None):
        self.client = client
        self.target_arn = target_arn
        self.role_arn = role_arn
        self.group_name = group_name

    def create_once(self, name: str, at: datetime, payload: dict) -> bool:
        """같은 이름이 이미 있으면(ConflictException) 만들지 않고 False."""
        kst = clock.parse_as_of(at)
        params = {
            "Name": name,
            "ScheduleExpression": f"at({kst.strftime('%Y-%m-%dT%H:%M:%S')})",
            "ScheduleExpressionTimezone": TIMEZONE,
            "ActionAfterCompletion": "DELETE",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": {"Arn": self.target_arn, "RoleArn": self.role_arn,
                       "Input": json.dumps({"oppSchedule": payload}, ensure_ascii=False, separators=(",", ":"))},
        }
        if self.group_name:
            params["GroupName"] = self.group_name
        try:
            self.client.create_schedule(**params)
        except ClientError as e:
            if error_code(e) == "ConflictException":
                return False
            raise aws_service_error(SERVICE) from e
        except BotoCoreError as e:
            raise aws_service_error(SERVICE) from e
        return True

    def delete(self, name: str) -> None:
        """없는 일정(ResourceNotFoundException)은 무시한다."""
        params = {"Name": name}
        if self.group_name:
            params["GroupName"] = self.group_name
        try:
            self.client.delete_schedule(**params)
        except ClientError as e:
            if error_code(e) != "ResourceNotFoundException":
                raise aws_service_error(SERVICE) from e
        except BotoCoreError as e:
            raise aws_service_error(SERVICE) from e
