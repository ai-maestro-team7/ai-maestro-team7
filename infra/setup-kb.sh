#!/usr/bin/env bash
# A 파트 Bedrock Knowledge Base 를 만든다. 여러 번 실행해도 안전하다(이미 있으면 건너뜀).
# 구성: 원천 KB_SOURCE_BUCKET/docs/ → 임베딩 Titan Text Embeddings V2(1024) → S3 Vectors KB_VECTOR_BUCKET/KB_VECTOR_INDEX
# 순서: 벡터 버킷·인덱스 → KB 서비스 역할 → KB → S3 데이터 소스. 원천 버킷은 setup-data.sh 가 만든다.
#
# 사용법
#   infra/setup-kb.sh                         자원만 만든다
#   infra/setup-kb.sh --upload <폴더>          지식 패키지 bedrock/documents/ 의 .md 와 .md.metadata.json 만 docs/ 에 올린다
#   infra/setup-kb.sh --sync                  동기화(ingestion)를 실행하고 끝날 때까지 기다린다
#   (둘 다 쓸 수 있다: --upload <폴더> --sync)
#
# KB 에는 bedrock/documents/ 13쌍만 올린다. agent/, raw/, structured/, 개인 문서는 올리지 않는다 (AGENTS.md).
# 계정 ID 와 KB ID 는 저장소에 적지 않는다. KB ID 는 실행 결과로 출력한다.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

UPLOAD_DIR=""
SYNC=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --upload) UPLOAD_DIR=${2:?--upload 뒤에 폴더 경로가 필요하다}; shift 2 ;;
    --sync) SYNC=true; shift ;;
    *) echo "알 수 없는 옵션: $1" >&2; exit 2 ;;
  esac
done

fill() { sed "s/\${ACCOUNT_ID}/${ACCOUNT_ID}/g" "$1"; }

# ---------------------------------------------------------------- 원천 문서 (선택)
if [[ -n $UPLOAD_DIR ]]; then
  echo "[S3] s3://${KB_SOURCE_BUCKET}/docs/"
  md=$(find "$UPLOAD_DIR" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
  meta=$(find "$UPLOAD_DIR" -maxdepth 1 -name '*.md.metadata.json' | wc -l | tr -d ' ')
  if [[ $md -eq 0 || $md -ne $meta ]]; then
    echo "  문서와 메타데이터 수가 맞지 않는다 (md=$md, metadata=$meta). 지식 패키지의 bedrock/documents/ 폴더인지 확인한다" >&2
    exit 1
  fi
  aws s3 cp "$UPLOAD_DIR" "s3://${KB_SOURCE_BUCKET}/docs/" --recursive \
    --exclude "*" --include "*.md" --include "*.md.metadata.json" --only-show-errors
  echo "  올림: md ${md}개 + metadata ${meta}개 (버킷 docs/ 객체 $(aws s3 ls "s3://${KB_SOURCE_BUCKET}/docs/" | wc -l | tr -d ' ')개)"
fi

# ---------------------------------------------------------------- S3 Vectors
echo "[S3 Vectors] ${KB_VECTOR_BUCKET}/${KB_VECTOR_INDEX}"
if aws s3vectors get-vector-bucket --vector-bucket-name "$KB_VECTOR_BUCKET" >/dev/null 2>&1; then
  echo "  = ${KB_VECTOR_BUCKET} (이미 있음)"
else
  aws s3vectors create-vector-bucket --vector-bucket-name "$KB_VECTOR_BUCKET" --tags team=$PREFIX >/dev/null
  echo "  + ${KB_VECTOR_BUCKET}"
fi
if aws s3vectors get-index --vector-bucket-name "$KB_VECTOR_BUCKET" --index-name "$KB_VECTOR_INDEX" >/dev/null 2>&1; then
  echo "  = ${KB_VECTOR_INDEX} (이미 있음)"
else
  # KB 가 청크 원문과 메타데이터를 이 두 키에 넣는다. 필터 가능 메타데이터 한도를 넘지 않도록 필터 불가로 둔다.
  # 빠지면 동기화가 실패한다 (Bedrock 사용자 가이드 "How content chunking works for knowledge bases")
  aws s3vectors create-index --vector-bucket-name "$KB_VECTOR_BUCKET" --index-name "$KB_VECTOR_INDEX" \
    --data-type float32 --dimension "$KB_EMBEDDING_DIM" --distance-metric cosine \
    --metadata-configuration '{"nonFilterableMetadataKeys":["AMAZON_BEDROCK_TEXT","AMAZON_BEDROCK_METADATA"]}' >/dev/null
  echo "  + ${KB_VECTOR_INDEX} (${KB_EMBEDDING_DIM}차원, 코사인)"
fi

# ---------------------------------------------------------------- KB 서비스 역할
echo "[IAM] ${KB_ROLE_NAME}"
role_created=false
if aws iam get-role --role-name "$KB_ROLE_NAME" >/dev/null 2>&1; then
  echo "  = ${KB_ROLE_NAME} (이미 있음)"
else
  aws iam create-role --role-name "$KB_ROLE_NAME" --assume-role-policy-document "$(fill iam/kb-trust-policy.json)" \
    --tags Key=team,Value=$PREFIX >/dev/null
  role_created=true
  echo "  + ${KB_ROLE_NAME}"
fi
aws iam put-role-policy --role-name "$KB_ROLE_NAME" --policy-name ${PREFIX}-kb-access \
  --policy-document "$(fill iam/kb-role-policy.json)"
echo "  정책 적용: $(aws iam get-role-policy --role-name "$KB_ROLE_NAME" --policy-name ${PREFIX}-kb-access --query 'PolicyDocument.Statement[].Sid' --output text)"
$role_created && sleep 10  # 새 역할이 Bedrock 에 보일 때까지

# ---------------------------------------------------------------- Knowledge Base
echo "[Bedrock] ${KB_NAME}"
KB_ID=$(aws bedrock-agent list-knowledge-bases --query "knowledgeBaseSummaries[?name=='${KB_NAME}'].knowledgeBaseId | [0]" --output text)
if [[ $KB_ID != "None" && -n $KB_ID ]]; then
  echo "  = ${KB_NAME} (이미 있음)"
else
  KB_ID=$(aws bedrock-agent create-knowledge-base --name "$KB_NAME" \
    --description "team07 A part: NCS job knowledge, fair hiring, counseling methodology" \
    --role-arn "arn:aws:iam::${ACCOUNT_ID}:role/${KB_ROLE_NAME}" \
    --knowledge-base-configuration "{\"type\":\"VECTOR\",\"vectorKnowledgeBaseConfiguration\":{\"embeddingModelArn\":\"arn:aws:bedrock:${AWS_REGION}::foundation-model/${KB_EMBEDDING_MODEL_ID}\",\"embeddingModelConfiguration\":{\"bedrockEmbeddingModelConfiguration\":{\"dimensions\":${KB_EMBEDDING_DIM},\"embeddingDataType\":\"FLOAT32\"}}}}" \
    --storage-configuration "{\"type\":\"S3_VECTORS\",\"s3VectorsConfiguration\":{\"indexArn\":\"arn:aws:s3vectors:${AWS_REGION}:${ACCOUNT_ID}:bucket/${KB_VECTOR_BUCKET}/index/${KB_VECTOR_INDEX}\"}}" \
    --tags team=$PREFIX --query knowledgeBase.knowledgeBaseId --output text)
  echo "  + ${KB_NAME}"
fi
for _ in $(seq 1 24); do
  status=$(aws bedrock-agent get-knowledge-base --knowledge-base-id "$KB_ID" --query knowledgeBase.status --output text)
  [[ $status == ACTIVE ]] && break
  [[ $status == FAILED ]] && { echo "  KB 생성 실패" >&2; exit 1; }
  sleep 5
done
echo "  상태: ${status}"

# ---------------------------------------------------------------- 데이터 소스
DS_ID=$(aws bedrock-agent list-data-sources --knowledge-base-id "$KB_ID" \
  --query "dataSourceSummaries[?name=='${KB_DATA_SOURCE_NAME}'].dataSourceId | [0]" --output text)
if [[ $DS_ID != "None" && -n $DS_ID ]]; then
  echo "  = 데이터 소스 ${KB_DATA_SOURCE_NAME} (이미 있음)"
else
  # 문서가 3~6KB 라 고정 300토큰, 겹침 20% 로 자른다
  DS_ID=$(aws bedrock-agent create-data-source --knowledge-base-id "$KB_ID" --name "$KB_DATA_SOURCE_NAME" \
    --data-source-configuration "{\"type\":\"S3\",\"s3Configuration\":{\"bucketArn\":\"arn:aws:s3:::${KB_SOURCE_BUCKET}\",\"inclusionPrefixes\":[\"docs/\"]}}" \
    --vector-ingestion-configuration '{"chunkingConfiguration":{"chunkingStrategy":"FIXED_SIZE","fixedSizeChunkingConfiguration":{"maxTokens":300,"overlapPercentage":20}}}' \
    --data-deletion-policy DELETE --query dataSource.dataSourceId --output text)
  echo "  + 데이터 소스 ${KB_DATA_SOURCE_NAME} (docs/ 만)"
fi

# ---------------------------------------------------------------- 동기화 (선택)
if $SYNC; then
  echo "[동기화]"
  JOB=$(aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" \
    --query ingestionJob.ingestionJobId --output text)
  for _ in $(seq 1 60); do
    read -r st scanned indexed failed < <(aws bedrock-agent get-ingestion-job --knowledge-base-id "$KB_ID" \
      --data-source-id "$DS_ID" --ingestion-job-id "$JOB" \
      --query 'ingestionJob.[status,statistics.numberOfDocumentsScanned,statistics.numberOfNewDocumentsIndexed,statistics.numberOfDocumentsFailed]' \
      --output text)
    [[ $st == COMPLETE || $st == FAILED || $st == STOPPED ]] && break
    sleep 5
  done
  echo "  상태 ${st}: 검사 ${scanned}, 새로 색인 ${indexed}, 실패 ${failed}"
  [[ $st == COMPLETE && $failed == 0 ]] || exit 1
fi

echo
echo "KB_ID=${KB_ID}   # Lambda 환경변수로 넣는다. 저장소에는 적지 않는다"
