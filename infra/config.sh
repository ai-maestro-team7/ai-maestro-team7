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

# Lambda 실행 역할 (infra/setup-role.sh 가 만든다)

ROLE_ARN=${ROLE_ARN:-arn:aws:iam::${ACCOUNT_ID}:role/${PREFIX}-lambda-role}

# Bedrock 모델 (코드에 넣지 않고 Lambda 환경 변수로, AGENTS.md "코딩 규칙"). 서울 리전은 global. 프로필로만 호출
MODEL_ID=${MODEL_ID:-global.anthropic.claude-haiku-5-5}
EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID:-cohere.embed-v4:0}

# 프론트 주소가 정해지면 바꾼다. 개발 중에는 * (모두 허용)
ALLOWED_ORIGIN=${ALLOWED_ORIGIN:-*}

TABLES=(career-mentor catalog reference cache)
