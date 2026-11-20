# team07 인프라 공통 설정. 다른 스크립트가 source 해서 쓴다.
export AWS_REGION=ap-northeast-2
export AWS_PAGER=""

PREFIX=team07
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

FUNCTION_NAME=${PREFIX}-api
API_NAME=${PREFIX}-http-api
UPLOAD_BUCKET=${PREFIX}-uploads-${ACCOUNT_ID}   # S3 버킷 이름은 전 세계에서 유일해야 해서 계정 ID를 붙임
WEB_BUCKET=${PREFIX}-web-${ACCOUNT_ID}
CAREER_DOCS_BUCKET=${PREFIX}-career-docs-${ACCOUNT_ID}   # 명세 §7.2 개인 문서 (users/{hash}/...)
KB_SOURCE_BUCKET=${PREFIX}-kb-source-${ACCOUNT_ID}       # 명세 §7.2 KB 원천 (docs/ 13쌍만)
OPP_DATA_BUCKET=${PREFIX}-opp-data-${ACCOUNT_ID}         # B: raw/, normalized/, seed/, snapshots/, runs/
OPP_VECTOR_BUCKET=${PREFIX}-opp-vectors                  # B: S3 Vectors, 인덱스 postings-v1
OPP_SECRET_ID=${OPP_SECRET_ID:-team07/opp-api-keys}
OPP_VECTOR_INDEX=postings-v1
CATALOG_TABLE=${PREFIX}-catalog

# A: Bedrock Knowledge Base (infra/setup-kb.sh). 원천 문서는 KB_SOURCE_BUCKET 의 docs/ 13쌍
KB_NAME=${PREFIX}-career-mentor-kb
KB_DATA_SOURCE_NAME=${PREFIX}-kb-docs
KB_ROLE_NAME=${PREFIX}-kb-role
KB_VECTOR_BUCKET=${PREFIX}-kb-vectors                    # B의 OPP_VECTOR_BUCKET 과 따로 둔다 (KB마다 벡터 저장소 하나)
KB_VECTOR_INDEX=career-mentor-kb-v1                      # 1024차원, 코사인. 바꾸면 iam/kb-role-policy.json 도 같이 바꾼다
# 서울 리전 KB가 지원하는 임베딩은 Titan Text Embeddings V2 (Cohere v4는 KB 미지원). B의 EMBEDDING_MODEL_ID 와 다르다
KB_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
KB_EMBEDDING_DIM=1024
# Bedrock 모델 (docs/team-guide.md). 코드에는 환경변수로만 넣는다
MODEL_ID=${MODEL_ID:-global.anthropic.claude-haiku-5-5}
EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID:-global.cohere.embed-v4:0}  # 서울 리전은 global. 프로필로만 호출 가능

# B 알림 일정: EventBridge Scheduler가 이 역할로 Lambda를 부른다 (infra/setup-role.sh 가 만든다)
SCHEDULER_ROLE_NAME=${PREFIX}-scheduler-role
SCHEDULER_ROLE_ARN=arn:aws:iam::${ACCOUNT_ID}:role/${SCHEDULER_ROLE_NAME}

# Lambda 실행 역할 (infra/setup-role.sh 가 만든다)

ROLE_ARN=${ROLE_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/${PREFIX}-lambda-role}


# 프론트 주소가 정해지면 바꾼다. 개발 중에는 * (모두 허용)
ALLOWED_ORIGIN=${ALLOWED_ORIGIN:-*}

TABLES=(career-mentor catalog reference cache)
