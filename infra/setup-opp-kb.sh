#!/usr/bin/env bash
# B(부산 기회 추천) 정책 검색용 Bedrock Knowledge Base를 만든다. 여러 번 실행해도 안전하다.
#   문서:   s3://team07-opp-data-<계정ID>/kb/policies/  (ai/busan-opportunity 의 ingest/policy_docs.py 가 만든다)
#   벡터:   S3 Vectors team07-opp-vectors / policy-kb-v1 (Titan Embed v2, 1024차원, 코사인)
#   역할:   team07-opp-kb-role (Bedrock이 문서를 읽고 임베딩해 벡터를 쓸 때 쓴다)
# Lambda는 기존 권한(KnowledgeBaseRetrieve)으로 검색하고, KB ID는 S3 seed/kb.json 에서 읽는다 (환경변수 추가 없음).
# 문서를 바꾼 뒤에는 이 스크립트를 다시 돌리면 색인을 다시 한다.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

KB_NAME=${PREFIX}-opp-policy-kb
KB_ROLE=${PREFIX}-opp-kb-role
KB_INDEX=policy-kb-v1
KB_PREFIX=kb/policies/
EMBED_ARN=arn:aws:bedrock:${AWS_REGION}::foundation-model/amazon.titan-embed-text-v2:0
INDEX_ARN=arn:aws:s3vectors:${AWS_REGION}:${ACCOUNT_ID}:bucket/${OPP_VECTOR_BUCKET}/index/${KB_INDEX}
ROLE_ARN_KB=arn:aws:iam::${ACCOUNT_ID}:role/${KB_ROLE}

echo "[S3 Vectors] $OPP_VECTOR_BUCKET / $KB_INDEX"
if aws s3vectors get-index --vector-bucket-name "$OPP_VECTOR_BUCKET" --index-name "$KB_INDEX" >/dev/null 2>&1; then
  echo "  = 인덱스 (이미 있음)"
else
  # Bedrock이 조각 글과 메타데이터 묶음을 넣는 두 키는 필터에 쓰지 않는다 (필터용 메타데이터는 2KB 제한)
  aws s3vectors create-index --vector-bucket-name "$OPP_VECTOR_BUCKET" --index-name "$KB_INDEX" \
    --data-type float32 --dimension 1024 --distance-metric cosine \
    --metadata-configuration '{"nonFilterableMetadataKeys":["AMAZON_BEDROCK_TEXT","AMAZON_BEDROCK_METADATA"]}' >/dev/null && echo "  + 인덱스"
fi

echo "[IAM] $KB_ROLE"
TRUST=$(cat <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"bedrock.amazonaws.com"},"Action":"sts:AssumeRole",
 "Condition":{"StringEquals":{"aws:SourceAccount":"${ACCOUNT_ID}"},"ArnLike":{"aws:SourceArn":"arn:aws:bedrock:${AWS_REGION}:${ACCOUNT_ID}:knowledge-base/*"}}}]}
JSON
)
POLICY=$(cat <<JSON
{"Version":"2012-10-17","Statement":[
 {"Sid":"ReadPolicyDocs","Effect":"Allow","Action":["s3:GetObject"],"Resource":"arn:aws:s3:::${OPP_DATA_BUCKET}/${KB_PREFIX}*"},
 {"Sid":"ListPolicyDocs","Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::${OPP_DATA_BUCKET}","Condition":{"StringLike":{"s3:prefix":["${KB_PREFIX}*"]}}},
 {"Sid":"Embed","Effect":"Allow","Action":["bedrock:InvokeModel"],"Resource":"${EMBED_ARN}"},
 {"Sid":"Vectors","Effect":"Allow","Action":["s3vectors:PutVectors","s3vectors:GetVectors","s3vectors:DeleteVectors","s3vectors:QueryVectors","s3vectors:GetIndex"],"Resource":"${INDEX_ARN}"}]}
JSON
)
if aws iam get-role --role-name "$KB_ROLE" >/dev/null 2>&1; then
  echo "  = 역할 (이미 있음)"
else
  aws iam create-role --role-name "$KB_ROLE" --assume-role-policy-document "$TRUST" --tags Key=team,Value=$PREFIX >/dev/null
  echo "  + 역할"
  sleep 10  # 역할이 퍼질 때까지
fi
aws iam put-role-policy --role-name "$KB_ROLE" --policy-name ${PREFIX}-opp-kb-policy --policy-document "$POLICY"

echo "[Bedrock] $KB_NAME"
KB_ID=$(aws bedrock-agent list-knowledge-bases --query "knowledgeBaseSummaries[?name=='${KB_NAME}'].knowledgeBaseId | [0]" --output text)
if [[ $KB_ID == None || -z $KB_ID ]]; then
  # 역할 정책이 퍼지기 전에는 Bedrock이 벡터 인덱스 권한 확인에 실패한다. 잠깐 기다렸다 몇 번 다시 시도한다
  KB_ID=""
  for attempt in 1 2 3 4 5 6; do
    KB_ID=$(aws bedrock-agent create-knowledge-base --name "$KB_NAME" --role-arn "$ROLE_ARN_KB" \
      --description "B: 청년정책 원문 검색 (온통청년)" --tags team=$PREFIX \
      --knowledge-base-configuration "{\"type\":\"VECTOR\",\"vectorKnowledgeBaseConfiguration\":{\"embeddingModelArn\":\"${EMBED_ARN}\",\"embeddingModelConfiguration\":{\"bedrockEmbeddingModelConfiguration\":{\"dimensions\":1024,\"embeddingDataType\":\"FLOAT32\"}}}}" \
      --storage-configuration "{\"type\":\"S3_VECTORS\",\"s3VectorsConfiguration\":{\"indexArn\":\"${INDEX_ARN}\"}}" \
      --query knowledgeBase.knowledgeBaseId --output text 2>/dev/null) && [[ -n $KB_ID ]] && break
    KB_ID=""
    sleep 15
  done
  [[ -n $KB_ID ]] || { echo "KB를 만들지 못했습니다 (역할 권한 확인)" >&2; exit 1; }
  echo "  + KB"
  for _ in $(seq 1 30); do
    [[ $(aws bedrock-agent get-knowledge-base --knowledge-base-id "$KB_ID" --query knowledgeBase.status --output text) == ACTIVE ]] && break
    sleep 5
  done
else
  echo "  = KB (이미 있음)"
fi

DS_ID=$(aws bedrock-agent list-data-sources --knowledge-base-id "$KB_ID" --query "dataSourceSummaries[?name=='${PREFIX}-opp-policy-docs'].dataSourceId | [0]" --output text)
if [[ $DS_ID == None || -z $DS_ID ]]; then
  # 정책 1건 = 문서 1개 = 조각 1개. 쪼개지 않는다 (NONE)
  DS_ID=$(aws bedrock-agent create-data-source --knowledge-base-id "$KB_ID" --name ${PREFIX}-opp-policy-docs \
    --data-source-configuration "{\"type\":\"S3\",\"s3Configuration\":{\"bucketArn\":\"arn:aws:s3:::${OPP_DATA_BUCKET}\",\"inclusionPrefixes\":[\"${KB_PREFIX}\"]}}" \
    --vector-ingestion-configuration '{"chunkingConfiguration":{"chunkingStrategy":"NONE"}}' \
    --query dataSource.dataSourceId --output text)
  echo "  + 데이터 소스"
else
  echo "  = 데이터 소스 (이미 있음)"
fi

JOB_ID=$(aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --query ingestionJob.ingestionJobId --output text)
echo "  색인 시작"
while :; do
  STATUS=$(aws bedrock-agent get-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --ingestion-job-id "$JOB_ID" --query ingestionJob.status --output text)
  [[ $STATUS == COMPLETE || $STATUS == FAILED || $STATUS == STOPPED ]] && break
  sleep 20
done
aws bedrock-agent get-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --ingestion-job-id "$JOB_ID" \
  --query 'ingestionJob.[status,statistics.numberOfDocumentsScanned,statistics.numberOfNewDocumentsIndexed,statistics.numberOfModifiedDocumentsIndexed,statistics.numberOfDocumentsFailed]' --output text

# Lambda가 KB ID를 읽는 곳 (공개 저장소에 ID를 적지 않는다)
printf '{"knowledgeBaseId": "%s"}\n' "$KB_ID" | aws s3 cp - "s3://${OPP_DATA_BUCKET}/seed/kb.json" --content-type application/json >/dev/null
echo "완료: seed/kb.json 갱신"
