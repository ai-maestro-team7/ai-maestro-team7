#!/usr/bin/env bash
# DynamoDB 테이블 5개와 업로드용 S3 버킷을 만든다. 여러 번 실행해도 안전하다(이미 있으면 건너뜀).
# 역할(ROLE_ARN) 없이 실행 가능.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

create_table() { # name pk [sk]
  local name=$1 pk=$2 sk=${3:-}
  if aws dynamodb describe-table --table-name "$name" >/dev/null 2>&1; then
    echo "  = $name (이미 있음)"; return
  fi
  local attrs="AttributeName=$pk,AttributeType=S" keys="AttributeName=$pk,KeyType=HASH"
  if [[ -n $sk ]]; then
    attrs="$attrs AttributeName=$sk,AttributeType=S"; keys="$keys AttributeName=$sk,KeyType=RANGE"
  fi
  # shellcheck disable=SC2086
  aws dynamodb create-table --table-name "$name" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions $attrs --key-schema $keys \
    --tags Key=team,Value=$PREFIX >/dev/null
  echo "  + $name"
}

enable_ttl() { # name attr
  aws dynamodb wait table-exists --table-name "$1"
  aws dynamodb update-time-to-live --table-name "$1" \
    --time-to-live-specification "Enabled=true,AttributeName=$2" >/dev/null 2>&1 || true
}

echo "[DynamoDB]"
create_table ${PREFIX}-cache      cache_key   # A: 외부 API 응답 캐시
enable_ttl   ${PREFIX}-cache expires_at
# (users·chat·jobs·interviews 테이블은 DB 스키마 v1.2에서 career-mentor로 합쳐 삭제함)

# 개발 명세서 v2.0 §7.1 — 멘토링 공통 단일 테이블 (PK/SK + GSI1, TTL은 임시 업로드/멱등 키에만)
echo "[DynamoDB] ${PREFIX}-career-mentor"
CM=${PREFIX}-career-mentor
if aws dynamodb describe-table --table-name "$CM" >/dev/null 2>&1; then
  echo "  = $CM (이미 있음)"
else
  aws dynamodb create-table --table-name "$CM" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
                            AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S \
    --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
    --global-secondary-indexes 'IndexName=GSI1,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH},{AttributeName=GSI1SK,KeyType=RANGE}],Projection={ProjectionType=ALL}' \
    --tags Key=team,Value=$PREFIX >/dev/null
  echo "  + $CM"
fi
enable_ttl "$CM" expiresAt

# 범용 키(PK/SK + GSI1) 테이블 만들기
pk_sk_table() { # name [extra args...]
  local name=$1; shift
  if aws dynamodb describe-table --table-name "$name" >/dev/null 2>&1; then echo "  = $name (이미 있음)"; return; fi
  aws dynamodb create-table --table-name "$name" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
                            AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S \
    --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
    --global-secondary-indexes 'IndexName=GSI1,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH},{AttributeName=GSI1SK,KeyType=RANGE}],Projection={ProjectionType=ALL}' \
    --tags Key=team,Value=$PREFIX "$@" >/dev/null
  echo "  + $name"
}

# A: NCS 직무·능력단위·자격 연계 + 고용24 직종코드 ↔ NCS 매핑 (DB 스키마 §4)
echo "[DynamoDB] ${PREFIX}-reference"
pk_sk_table ${PREFIX}-reference

# B 피드백 v0.1 — 공고·정책·기업 (B 수집 배치만 쓰고, 다른 파트는 읽기만). Streams는 B-12(P1)용
echo "[DynamoDB] ${PREFIX}-catalog"
CAT=${PREFIX}-catalog
if aws dynamodb describe-table --table-name "$CAT" >/dev/null 2>&1; then
  echo "  = $CAT (이미 있음)"
else
  aws dynamodb create-table --table-name "$CAT" --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
                            AttributeName=GSI1PK,AttributeType=S AttributeName=GSI1SK,AttributeType=S \
    --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
    --global-secondary-indexes 'IndexName=GSI1,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH},{AttributeName=GSI1SK,KeyType=RANGE}],Projection={ProjectionType=ALL}' \
    --stream-specification StreamEnabled=true,StreamViewType=NEW_IMAGE \
    --tags Key=team,Value=$PREFIX >/dev/null
  echo "  + $CAT (Streams NEW_IMAGE)"
fi

# 비공개 버킷: 이름 · 수명주기 규칙(선택)
private_bucket() { # name [lifecycle-json]
  local b=$1 lc=${2:-}
  if aws s3api head-bucket --bucket "$b" >/dev/null 2>&1; then
    echo "  = $b (이미 있음)"
  else
    aws s3api create-bucket --bucket "$b" --create-bucket-configuration LocationConstraint=$AWS_REGION >/dev/null
    echo "  + $b"
  fi
  aws s3api put-public-access-block --bucket "$b" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-encryption --bucket "$b" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-bucket-tagging --bucket "$b" --tagging "TagSet=[{Key=team,Value=$PREFIX}]"
  [[ -n $lc ]] && aws s3api put-bucket-lifecycle-configuration --bucket "$b" --lifecycle-configuration "$lc"
  return 0
}

# 명세 §7.2 — 개인 문서(이력서 등) / KB 원천 문서 분리
echo "[S3] 멘토링 버킷"
private_bucket "$CAREER_DOCS_BUCKET"
aws s3api put-bucket-cors --bucket "$CAREER_DOCS_BUCKET" --cors-configuration \
  "{\"CORSRules\":[{\"AllowedOrigins\":[\"$ALLOWED_ORIGIN\"],\"AllowedMethods\":[\"PUT\"],\"AllowedHeaders\":[\"*\"],\"MaxAgeSeconds\":3000}]}"
private_bucket "$KB_SOURCE_BUCKET"
private_bucket "$OPP_DATA_BUCKET"   # B: 공공 API 원본·정규화본·시드·데모 스냅샷·수집 기록

echo "[S3] $UPLOAD_BUCKET"
if aws s3api head-bucket --bucket "$UPLOAD_BUCKET" >/dev/null 2>&1; then
  echo "  = 이미 있음"
else
  aws s3api create-bucket --bucket "$UPLOAD_BUCKET" \
    --create-bucket-configuration LocationConstraint=$AWS_REGION >/dev/null
  echo "  + 생성"
fi
aws s3api put-public-access-block --bucket "$UPLOAD_BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-lifecycle-configuration --bucket "$UPLOAD_BUCKET" --lifecycle-configuration \
  '{"Rules":[{"ID":"expire-uploads-7d","Status":"Enabled","Filter":{"Prefix":"uploads/"},"Expiration":{"Days":7}}]}'
aws s3api put-bucket-cors --bucket "$UPLOAD_BUCKET" --cors-configuration \
  "{\"CORSRules\":[{\"AllowedOrigins\":[\"$ALLOWED_ORIGIN\"],\"AllowedMethods\":[\"PUT\",\"GET\"],\"AllowedHeaders\":[\"*\"],\"MaxAgeSeconds\":3000}]}"
aws s3api put-bucket-tagging --bucket "$UPLOAD_BUCKET" --tagging "TagSet=[{Key=team,Value=$PREFIX}]"
echo "  비공개 · 7일 자동 삭제 · 브라우저 PUT CORS 설정 완료"

# B: 공고 임베딩 검색 (S3 Vectors). 사용자 권한: infra/iam/dev-user-s3vectors.json (team07-* 한정)
echo "[S3 Vectors] $OPP_VECTOR_BUCKET / postings-v1"
if aws s3vectors get-vector-bucket --vector-bucket-name "$OPP_VECTOR_BUCKET" >/dev/null 2>&1; then
  echo "  = 버킷 이미 있음"
else
  aws s3vectors create-vector-bucket --vector-bucket-name "$OPP_VECTOR_BUCKET" >/dev/null && echo "  + 버킷"
fi
if aws s3vectors get-index --vector-bucket-name "$OPP_VECTOR_BUCKET" --index-name postings-v1 >/dev/null 2>&1; then
  echo "  = 인덱스 이미 있음"
else
  # 1024차원(B 설정 embedDim), 코사인, title은 필터 불가 메타데이터
  aws s3vectors create-index --vector-bucket-name "$OPP_VECTOR_BUCKET" --index-name postings-v1 \
    --data-type float32 --dimension 1024 --distance-metric cosine \
    --metadata-configuration '{"nonFilterableMetadataKeys":["title"]}' >/dev/null && echo "  + 인덱스"
fi

# 특정 시점 복구(PITR): 지난 35일 안 어느 시점으로든 테이블을 되돌릴 수 있게 (시연 전 실수 대비)
echo "[DynamoDB] 특정 시점 복구"
for t in "${TABLES[@]}"; do
  aws dynamodb update-continuous-backups --table-name "${PREFIX}-$t" \
    --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true >/dev/null && echo "  = ${PREFIX}-$t"
done
