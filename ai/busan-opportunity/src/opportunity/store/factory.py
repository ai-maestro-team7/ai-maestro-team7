"""AWS 구현으로 `Deps`를 만든다. 입구(REST·Agent·배치)가 콜드 스타트에 한 번 부른다.

환경변수는 `config.require_env`로 읽는다. 없으면 이름을 담은 오류로 멈추고 기본값으로 대신하지 않는다.

| 환경변수 | 쓰는 곳 |
|---|---|
| `TABLE_CATALOG`, `TABLE_CAREER_MENTOR` | DynamoDB 테이블 |
| `OPP_VECTOR_BUCKET`, `OPP_VECTOR_INDEX` | S3 Vectors |
| `MODEL_ID`, `EMBEDDING_MODEL_ID` | Bedrock LLM·임베딩 |
| `SCHEDULER_TARGET_ARN`, `SCHEDULER_ROLE_ARN` | EventBridge Scheduler 일정이 부를 Lambda와 그 역할 |
| `SCHEDULER_GROUP` (선택) | 일정 그룹. 없으면 default 그룹 |
| `SES_FROM_ADDRESS`, `COGNITO_USER_POOL_ID` (선택, 둘 다 있어야) | 메일 알림. 없으면 알림함만 쓴다 |
| `OPP_DATA_BUCKET` | `build_raw_store()`. 수집 배치만 쓴다 |
"""

import os
from functools import lru_cache

import boto3

from ..config import OpportunityConfig, get_config, require_env
from ..deps import Deps
from ..models.region import RegionStats
from ..ports import EligibilityFn, WorkspacePort
from .dynamo import DynamoCatalog, DynamoUsers
from .events import EmfEvents
from .mailer import SesMailer, cognito_email_resolver
from .s3 import S3RawStore
from .scheduler import EventBridgeScheduler
from .secrets import SecretsManagerSecrets
from .vectors import S3VectorIndex


# boto3 클라이언트는 프로세스에서 한 번만 만든다 (Lambda 웜 스타트에서 재사용)
@lru_cache(maxsize=None)
def _client(service: str, region: str):
    return boto3.client(service, region_name=region)


@lru_cache(maxsize=None)
def _dynamodb(region: str):
    return boto3.resource("dynamodb", region_name=region)


def build_aws_deps(*, eligibility: EligibilityFn, workspaces: WorkspacePort,
                   config: OpportunityConfig | None = None) -> Deps:
    """eligibility는 `backend/eligibility.py`의 판정 함수, workspaces는 공통 워크스페이스 어댑터다. 입구가 넣어 준다."""
    # 다른 워크트리(enrich)가 만든다. 없으면 import 오류를 그대로 올린다
    from ..enrich.bedrock import BedrockEmbedder, BedrockLlm

    config = config or get_config()
    region = config.region
    bedrock = _client("bedrock-runtime", region)
    resource = _dynamodb(region)

    mailer = None
    from_address, pool_id = os.environ.get("SES_FROM_ADDRESS"), os.environ.get("COGNITO_USER_POOL_ID")
    if from_address and pool_id:
        mailer = SesMailer(_client("sesv2", region), from_address=from_address,
                           resolve_email=cognito_email_resolver(_client("cognito-idp", region), pool_id))

    return Deps(
        config=config,
        catalog=DynamoCatalog(resource, require_env("TABLE_CATALOG")),
        users=DynamoUsers(resource, require_env("TABLE_CAREER_MENTOR"),
                          retention_days=config.notifications.retention_days),
        vectors=S3VectorIndex(_client("s3vectors", region), require_env("OPP_VECTOR_BUCKET"),
                              require_env("OPP_VECTOR_INDEX")),
        embedder=BedrockEmbedder(client=bedrock, config=config, model_id=require_env("EMBEDDING_MODEL_ID")),
        eligibility=eligibility,
        workspaces=workspaces,
        scheduler=EventBridgeScheduler(_client("scheduler", region), target_arn=require_env("SCHEDULER_TARGET_ARN"),
                                       role_arn=require_env("SCHEDULER_ROLE_ARN"),
                                       group_name=os.environ.get("SCHEDULER_GROUP") or None),
        events=EmfEvents(),
        llm=BedrockLlm(client=bedrock, config=config, model_id=require_env("MODEL_ID")),
        mailer=mailer,
        region_stats=RegionStats(),  # 주거비·통근 통계는 비워 둔다. 값이 없으면 비교 패널이 해당 행을 숨긴다
    )


def build_raw_store(config: OpportunityConfig | None = None) -> S3RawStore:
    """수집 배치용 S3 (`OPP_DATA_BUCKET`)."""
    return S3RawStore(_client("s3", (config or get_config()).region), require_env("OPP_DATA_BUCKET"))


def build_secrets(config: OpportunityConfig | None = None) -> SecretsManagerSecrets:
    """수집 배치용 Secrets Manager."""
    return SecretsManagerSecrets(_client("secretsmanager", (config or get_config()).region),
                                 json_secret_id=os.environ.get("OPP_SECRET_ID") or None)
