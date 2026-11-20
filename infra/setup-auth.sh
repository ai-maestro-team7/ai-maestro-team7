#!/usr/bin/env bash
# 로그인(아이디·비밀번호) — Cognito 사용자 풀 + 앱 클라이언트 + API JWT 검사. 여러 번 실행해도 안전하다.
#  - 토큰 없이 부르는 경로: POST /api/v1/auth/login, POST /api/v1/auth/refresh, GET /api/v1/health,
#    GET /api/v1/opportunities/public/postings (로그인 없이 보는 채용 공고 목록, B-D10)
#  - 그 밖의 모든 경로($default): Authorization: Bearer {accessToken} 필수
# 순서: setup-api.sh 다음에 실행
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

POOL_NAME=${PREFIX}-users
CLIENT_NAME=${PREFIX}-web

echo "[Cognito] $POOL_NAME"
POOL_ID=$(aws cognito-idp list-user-pools --max-results 60 --query "UserPools[?Name=='$POOL_NAME'].Id | [0]" --output text)
if [[ $POOL_ID == None || -z $POOL_ID ]]; then
  # 관리자만 계정 생성(데모 계정) · 아이디 로그인 · 비밀번호 8자 이상
  POOL_ID=$(aws cognito-idp create-user-pool --pool-name "$POOL_NAME" \
    --policies 'PasswordPolicy={MinimumLength=8,RequireUppercase=false,RequireLowercase=true,RequireNumbers=true,RequireSymbols=false}' \
    --admin-create-user-config AllowAdminCreateUserOnly=true \
    --username-configuration CaseSensitive=false \
    --user-pool-tags team=$PREFIX --query UserPool.Id --output text)
  echo "  + 사용자 풀 ($POOL_ID)"
else
  echo "  = 사용자 풀 ($POOL_ID)"
fi

CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" --query "UserPoolClients[?ClientName=='$CLIENT_NAME'].ClientId | [0]" --output text)
if [[ $CLIENT_ID == None || -z $CLIENT_ID ]]; then
  # 브라우저용이라 클라이언트 비밀값 없음. 액세스 토큰 1시간, 갱신 토큰 30일
  CLIENT_ID=$(aws cognito-idp create-user-pool-client --user-pool-id "$POOL_ID" --client-name "$CLIENT_NAME" \
    --no-generate-secret --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH \
    --prevent-user-existence-errors ENABLED \
    --access-token-validity 1 --id-token-validity 1 --refresh-token-validity 30 \
    --token-validity-units AccessToken=hours,IdToken=hours,RefreshToken=days \
    --query UserPoolClient.ClientId --output text)
  echo "  + 앱 클라이언트"
else
  echo "  = 앱 클라이언트"
fi

echo "[Lambda] COGNITO_CLIENT_ID 환경 변수"
CUR=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query 'Environment.Variables' --output json)
NEW=$(echo "$CUR" | python3 -c "import sys,json; d=json.load(sys.stdin) or {}; d['COGNITO_CLIENT_ID']='$CLIENT_ID'; d.pop('ALLOW_DEV_USER_HEADER', None); print(json.dumps({'Variables': d}))")
aws lambda update-function-configuration --function-name "$FUNCTION_NAME" --environment "$NEW" >/dev/null
aws lambda wait function-updated --function-name "$FUNCTION_NAME"
echo "  = 적용 (X-User-Id 개발용 헤더는 꺼짐)"

echo "[API Gateway] JWT 검사"
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)
ISSUER="https://cognito-idp.$AWS_REGION.amazonaws.com/$POOL_ID"
AUTH_ID=$(aws apigatewayv2 get-authorizers --api-id "$API_ID" --query "Items[?Name=='${PREFIX}-cognito'].AuthorizerId | [0]" --output text)
if [[ $AUTH_ID == None || -z $AUTH_ID ]]; then
  # 액세스 토큰은 aud 대신 client_id를 검사한다 (HTTP API JWT authorizer 동작)
  AUTH_ID=$(aws apigatewayv2 create-authorizer --api-id "$API_ID" --name ${PREFIX}-cognito --authorizer-type JWT \
    --identity-source '$request.header.Authorization' \
    --jwt-configuration "Audience=$CLIENT_ID,Issuer=$ISSUER" --query AuthorizerId --output text)
  echo "  + authorizer"
else
  aws apigatewayv2 update-authorizer --api-id "$API_ID" --authorizer-id "$AUTH_ID" --jwt-configuration "Audience=$CLIENT_ID,Issuer=$ISSUER" >/dev/null
  echo "  = authorizer"
fi

TARGET=$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='\$default'].Target | [0]" --output text)
for KEY in "POST /api/v1/auth/login" "POST /api/v1/auth/refresh" "GET /api/v1/health" \
           "GET /api/v1/opportunities/public/postings"; do
  RID=$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='$KEY'].RouteId | [0]" --output text)
  if [[ $RID == None || -z $RID ]]; then
    aws apigatewayv2 create-route --api-id "$API_ID" --route-key "$KEY" --target "$TARGET" --authorization-type NONE >/dev/null
    echo "  + 공개 경로: $KEY"
  fi
done
DEF=$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='\$default'].RouteId | [0]" --output text)
aws apigatewayv2 update-route --api-id "$API_ID" --route-id "$DEF" --authorization-type JWT --authorizer-id "$AUTH_ID" >/dev/null
echo "  = 나머지 경로(\$default): 토큰 필수"

echo
echo "COGNITO_USER_POOL_ID=$POOL_ID"
echo "COGNITO_CLIENT_ID=$CLIENT_ID"
