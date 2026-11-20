"""Build production mentoring dependencies from environment-only resource names."""
from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from botocore.config import Config

from mentoring.config import MentoringConfig, get_config, require_env
from mentoring.deps import Deps
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


def build_aws_deps(
    *,
    hash_user_id: Callable[[str], str],
    config: MentoringConfig | None = None,
) -> Deps:
    """Create the dependencies used by the backend mentoring entry points.

    Resource identifiers and the model ID deliberately have no defaults.
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
        hash_user_id=hash_user_id,
        reference=reference,
    )
