"""Build production mentoring dependencies from environment-only resource names."""
from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from botocore.config import Config

from mentoring.config import MentoringConfig, get_config, require_env
from mentoring.core.pdf_extractor import PdfExtractor
from mentoring.deps import Deps
from mentoring.extract import TextractOcr
from mentoring.llm.bedrock import BedrockLlm
from mentoring.reference import DynamoReferenceLookup
from mentoring.text_tools import load_text_tools

from .dispatch import LambdaTaskDispatcher
from .dynamo import DynamoUserRepo
from .reference_adapter import ReferenceUnitAdapter
from .s3 import S3ObjectStore


def _service_config(*, read_timeout: int = 60) -> Config:
    return Config(
        connect_timeout=5,
        read_timeout=read_timeout,
        retries={"mode": "standard", "max_attempts": 1},
    )


@lru_cache(maxsize=None)
def _dynamodb_resource(region: str) -> Any:
    import boto3

    return boto3.resource("dynamodb", region_name=region, config=_service_config())


@lru_cache(maxsize=None)
def _client(service: str, region: str) -> Any:
    import boto3

    return boto3.client(service, region_name=region, config=_service_config())


def _hash_user_id_not_set(user_id: str) -> str:
    raise RuntimeError("hash_user_id가 연결되지 않았습니다. 백엔드 공통 함수를 넣어야 합니다 (BE-6).")


def build_aws_deps(
    *,
    hash_user_id: Callable[[str], str] | None = None,
    config: MentoringConfig | None = None,
) -> Deps:
    """Create the dependencies used by the backend mentoring entry points.

    Resource identifiers and the model ID deliberately have no defaults.
    `hash_user_id`를 넣지 않으면 쓰일 때 오류를 낸다. 백엔드(`backend/mentoring_api.py`)는
    인자 없이 부른 뒤 `backend/common.py`의 `hash_user_id`로 바꿔 넣는다.
    """
    table_name = require_env("TABLE_CAREER_MENTOR")
    bucket = require_env("CAREER_DOCS_BUCKET")
    model_id = require_env("MODEL_ID")
    function_name = require_env("AWS_LAMBDA_FUNCTION_NAME")
    region = require_env("AWS_REGION")

    dynamodb = _dynamodb_resource(region)
    reference = None
    reference_table = os.environ.get("TABLE_REFERENCE", "").strip()
    if reference_table:
        reference = ReferenceUnitAdapter(DynamoReferenceLookup(dynamodb.Table(reference_table)))

    return Deps(
        config=config or get_config(),
        users=DynamoUserRepo(dynamodb.Table(table_name)),
        objects=S3ObjectStore(_client("s3", region), bucket),
        llm=BedrockLlm(_client("bedrock-runtime", region), model_id),
        tasks=LambdaTaskDispatcher(_client("lambda", region), function_name),
        text=load_text_tools(),
        hash_user_id=hash_user_id or _hash_user_id_not_set,
        reference=reference,
        # 텍스트 레이어 먼저, 부족할 때만 Textract OCR (이슈 #41 결정). OCR은 career-docs 원본을 직접 읽는다
        extractor=PdfExtractor(ocr=TextractOcr(_client("textract", region)), bucket=bucket),
    )
