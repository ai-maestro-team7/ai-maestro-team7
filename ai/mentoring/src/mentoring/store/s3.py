"""S3 object storage adapter."""
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError


@dataclass(frozen=True)
class S3ObjectInfo:
    size_bytes: int
    content_type: str | None


def _missing(error: ClientError) -> bool:
    return str(error.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}


class S3ObjectStore:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put_text(self, key: str, text: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )

    def get_text(self, key: str) -> str | None:
        data = self.get_bytes(key)
        return data.decode("utf-8") if data is not None else None

    def get_bytes(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if _missing(error):
                return None
            raise
        return response["Body"].read()

    def presign_put(self, key: str, *, content_type: str, size_bytes: int, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size_bytes,
            },
            ExpiresIn=expires_in,
        )

    def head(self, key: str) -> S3ObjectInfo | None:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if _missing(error):
                return None
            raise
        return S3ObjectInfo(
            size_bytes=int(response["ContentLength"]),
            content_type=response.get("ContentType"),
        )

    def copy(self, source_key: str, target_key: str) -> None:
        # 서버 안 복사라 Lambda가 파일을 내려받지 않는다. MetadataDirective 기본값(COPY)으로 형식이 그대로 간다
        self._client.copy_object(
            Bucket=self._bucket,
            Key=target_key,
            CopySource={"Bucket": self._bucket, "Key": source_key},
        )

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
