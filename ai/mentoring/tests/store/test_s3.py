from urllib.parse import parse_qs, urlparse

import boto3
from moto import mock_aws

from mentoring.store.s3 import S3ObjectStore


def test_s3_round_trip_head_presign_and_missing():
    with mock_aws():
        client = boto3.client("s3", region_name="ap-northeast-2")
        client.create_bucket(
            Bucket="team07-test-docs",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"},
        )
        store = S3ObjectStore(client, "team07-test-docs")
        store.put_text("users/hash/document.txt", "가상 이력서")
        assert store.get_text("users/hash/document.txt") == "가상 이력서"
        assert store.get_bytes("users/hash/document.txt") == "가상 이력서".encode()
        info = store.head("users/hash/document.txt")
        assert info.size_bytes == len("가상 이력서".encode())
        assert info.content_type == "text/plain; charset=utf-8"
        url = store.presign_put(
            "users/hash/upload.pdf", content_type="application/pdf", size_bytes=123, expires_in=300
        )
        signed = parse_qs(urlparse(url).query).get("X-Amz-SignedHeaders", [""])[0]
        assert "content-type" in signed
        assert store.get_text("missing") is None
        assert store.head("missing") is None
        store.delete("users/hash/document.txt")
        assert store.get_bytes("users/hash/document.txt") is None
