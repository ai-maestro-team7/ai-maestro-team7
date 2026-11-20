#!/usr/bin/env bash
# Lambda 함수 + HTTP API(CORS 포함)를 만들고 연결한다. 여러 번 실행해도 안전하다.
# 필요: 실행 역할 (infra/setup-role.sh)
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

if ! aws iam get-role --role-name "${ROLE_ARN##*/}" >/dev/null 2>&1; then
  echo "실행 역할이 없습니다. 먼저 ./setup-role.sh 를 실행하세요." >&2
  exit 1
fi

ZIP=$(./package.sh)
# setup-auth.sh가 만든 로그인 설정이 있으면 유지 (이 스크립트를 다시 돌려도 로그인이 꺼지지 않게)
POOL_ID=$(aws cognito-idp list-user-pools --max-results 60 --query "UserPools[?Name=='${PREFIX}-users'].Id | [0]" --output text 2>/dev/null || echo None)
CLIENT_ID=""
if [[ $POOL_ID != None && -n $POOL_ID ]]; then
  CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" --query "UserPoolClients[?ClientName=='${PREFIX}-web'].ClientId | [0]" --output text)
fi
# B(부산 기회 추천)가 쓰는 값: 공고·정책 테이블, 벡터 인덱스, 원본 버킷, 모델, 알림 일정
FUNCTION_ARN_EXPECTED=arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}
OPP_VARS="TABLE_CATALOG=$CATALOG_TABLE,OPP_VECTOR_BUCKET=$OPP_VECTOR_BUCKET,OPP_VECTOR_INDEX=$OPP_VECTOR_INDEX,OPP_DATA_BUCKET=$OPP_DATA_BUCKET,OPP_SECRET_ID=$OPP_SECRET_ID,MODEL_ID=$MODEL_ID,EMBEDDING_MODEL_ID=$EMBEDDING_MODEL_ID,SCHEDULER_TARGET_ARN=$FUNCTION_ARN_EXPECTED,SCHEDULER_ROLE_ARN=$SCHEDULER_ROLE_ARN"
ENV_VARS="Variables={UPLOAD_BUCKET=$UPLOAD_BUCKET,CAREER_DOCS_BUCKET=$CAREER_DOCS_BUCKET,TABLE_CAREER_MENTOR=${PREFIX}-career-mentor,TABLE_REFERENCE=${PREFIX}-reference,TABLE_CACHE=${PREFIX}-cache,ALLOWED_ORIGIN=$ALLOWED_ORIGIN,COGNITO_CLIENT_ID=${CLIENT_ID},$OPP_VARS}"

# 환경 변수는 지금 값에 이 스크립트가 관리하는 값(ENV_VARS)만 덮어쓴다.
# 다른 스크립트가 넣은 값(setup-social-login.sh 의 COGNITO_DOMAIN·SOCIAL_PROVIDERS 등)을 지우지 않기 위해서다
env_json() {
  CUR=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query 'Environment.Variables' --output json 2>/dev/null || echo null)
  echo "$CUR" | ENV_VARS="$ENV_VARS" python3 -c '
import json, os, sys
d = json.load(sys.stdin) or {}
managed = os.environ["ENV_VARS"].removeprefix("Variables={").removesuffix("}")
for pair in managed.split(","):
    k, _, v = pair.partition("=")
    d[k] = v
print(json.dumps({"Variables": d}))'
}

echo "[Lambda] $FUNCTION_NAME"
if aws lambda get-function --function-name "$FUNCTION_NAME" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FUNCTION_NAME" --zip-file "fileb://$ZIP" >/dev/null
  aws lambda wait function-updated --function-name "$FUNCTION_NAME"
  aws lambda update-function-configuration --function-name "$FUNCTION_NAME" --environment "$(env_json)" --timeout 900 --memory-size 1024 >/dev/null
  echo "  = 코드·설정 갱신"
else
  aws lambda create-function --function-name "$FUNCTION_NAME" \
    --runtime python3.13 --architectures arm64 --handler app.lambda_handler \
    --role "$ROLE_ARN" --zip-file "fileb://$ZIP" \
    --timeout 900 --memory-size 1024 --environment "$(env_json)" \
    --tags team=$PREFIX >/dev/null
  echo "  + 생성"
fi
aws lambda wait function-active-v2 --function-name "$FUNCTION_NAME"
FUNCTION_ARN=$(aws lambda get-function --function-name "$FUNCTION_NAME" --query Configuration.FunctionArn --output text)

echo "[API Gateway] $API_NAME"
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)
CORS="AllowOrigins=$ALLOWED_ORIGIN,AllowMethods=GET,POST,PUT,PATCH,DELETE,OPTIONS,AllowHeaders=content-type,authorization,x-user-id,idempotency-key,MaxAge=3600"
if [[ $API_ID == None || -z $API_ID ]]; then
  # quick create: $default 라우트 + Lambda 프록시 통합 + $default 스테이지(자동 배포)
  API_ID=$(aws apigatewayv2 create-api --name "$API_NAME" --protocol-type HTTP \
    --target "$FUNCTION_ARN" --cors-configuration "$CORS" \
    --tags team=$PREFIX --query ApiId --output text)
  echo "  + 생성 ($API_ID)"
else
  aws apigatewayv2 update-api --api-id "$API_ID" --cors-configuration "$CORS" >/dev/null
  echo "  = CORS 갱신 ($API_ID)"
fi

# API Gateway가 Lambda를 호출할 수 있게 허용 (이미 있으면 무시)
aws lambda add-permission --function-name "$FUNCTION_NAME" \
  --statement-id ${PREFIX}-apigw-invoke --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$AWS_REGION:$ACCOUNT_ID:$API_ID/*" >/dev/null 2>&1 || true

# 호출 제한: 인증이 붙기 전까지 크레딧 보호용 (초당 20건, 순간 50건). 시연 때 부족하면 올린다
aws apigatewayv2 update-stage --api-id "$API_ID" --stage-name '$default' \
  --default-route-settings ThrottlingRateLimit=${API_RATE_LIMIT:-20},ThrottlingBurstLimit=${API_BURST_LIMIT:-50} >/dev/null
echo "  = 호출 제한 ${API_RATE_LIMIT:-20}/s, 순간 ${API_BURST_LIMIT:-50}"

ENDPOINT=$(aws apigatewayv2 get-api --api-id "$API_ID" --query ApiEndpoint --output text)
echo
echo "API_BASE=$ENDPOINT"
echo "확인: curl $ENDPOINT/health"
