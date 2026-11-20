"""S3 구현. 버킷 `team07-opp-data-<계정ID>`(환경변수 `OPP_DATA_BUCKET`).

경로: raw/{출처}/{날짜}/, normalized/{날짜}/, seed/, snapshots/, runs/{날짜}.json
"""

from botocore.exceptions import BotoCoreError, ClientError

from ..config import require_env
from ..models.errors import aws_service_error
from .dynamo import aws_errors, error_code

SERVICE = "s3"


class S3RawStore:
    def __init__(self, client=None, bucket: str | None = None):
        if client is None:
            import boto3
            client = boto3.client(SERVICE)
        self.client = client
        self.bucket = bucket or require_env("OPP_DATA_BUCKET")

    def put(self, key: str, body: bytes, content_type: str = "application/json") -> None:
        with aws_errors(SERVICE):
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        """없는 키는 None."""
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as e:
            if error_code(e) in ("NoSuchKey", "404"):
                return None
            raise aws_service_error(SERVICE) from e
        except BotoCoreError as e:
            raise aws_service_error(SERVICE) from e

    def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        token = None
        while True:
            params = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                params["ContinuationToken"] = token
            with aws_errors(SERVICE):
                page = self.client.list_objects_v2(**params)
            keys += [row["Key"] for row in page.get("Contents", [])]
            token = page.get("NextContinuationToken")
            if not token:
                return sorted(keys)
