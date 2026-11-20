#!/usr/bin/env bash
# 소셜 로그인(Google·카카오) — Cognito 외부 로그인 + 앱 클라이언트 OAuth 설정 + 공개 경로. 여러 번 실행해도 안전하다. (이슈 #98)
#  - 토큰 없이 부르는 경로: GET /api/v1/auth/social/providers, POST /api/v1/auth/social/start, POST /api/v1/auth/social/token
#  - 제공자에게는 openid만 요청한다 (이름·이메일·전화번호를 받지 않는다)
# 순서: setup-api.sh → setup-auth.sh → setup-web.sh → 이 스크립트
#  - setup-api.sh는 Lambda 환경 변수를 통째로 다시 쓴다. 그 뒤에는 이 스크립트를 다시 돌려 COGNITO_DOMAIN·SOCIAL_PROVIDERS를 되살린다
#
# 처음 한 번:
#  1) 비밀값 없이 실행 → 사용자 풀 도메인을 만들고 리디렉트 주소(https://{도메인}/oauth2/idpresponse)를 출력한다
#  2) 그 주소를 Google Cloud Console(OAuth 클라이언트 "승인된 리디렉션 URI")과
#     Kakao Developers(카카오 로그인 Redirect URI, OpenID Connect 활성화)에 등록하고 클라이언트 ID·비밀값을 받는다
#  3) Secrets Manager $SOCIAL_SECRET_ID 에 {"google": {"clientId", "clientSecret"}, "kakao": {"clientId", "clientSecret"}} 저장
#     (없는 제공자는 빼도 된다. 값은 이 스크립트가 출력하지 않는다)
#  4) 다시 실행 → 외부 로그인 제공자, 앱 클라이언트, API 경로, Lambda 환경 변수를 맞춘다
#
# 미확인 (실제 계정에서 아직 확인하지 않았다):
#  - 사용자 풀이 AllowAdminCreateUserOnly=true(관리자만 계정 생성)인데, 외부 로그인 사용자가 처음 들어올 때 Cognito가 계정을 만들어 주는지
#  - 카카오를 OIDC 제공자(oidc_issuer=https://kauth.kakao.com)로 붙였을 때 Cognito의 discovery·토큰 교환·id_token 검증이 맞는지
#    (카카오 쪽 클라이언트 시크릿 사용 여부, 토큰 요청에 시크릿을 보내는 방식 포함)
#  - Google 제공자를 authorize_scopes=openid 하나로만 만들 수 있는지
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

POOL_NAME=${PREFIX}-users
CLIENT_NAME=${PREFIX}-web
DIST_COMMENT=${PREFIX}-web
LOCAL_CALLBACK=http://localhost:3000/login/callback/
umask 077
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

POOL_ID=$(aws cognito-idp list-user-pools --max-results 60 --query "UserPools[?Name=='$POOL_NAME'].Id | [0]" --output text)
if [[ $POOL_ID == None || -z $POOL_ID ]]; then
  echo "사용자 풀 $POOL_NAME 이 없습니다. 먼저 ./setup-auth.sh 를 실행하세요." >&2
  exit 1
fi
CLIENT_ID=$(aws cognito-idp list-user-pool-clients --user-pool-id "$POOL_ID" --query "UserPoolClients[?ClientName=='$CLIENT_NAME'].ClientId | [0]" --output text)
if [[ $CLIENT_ID == None || -z $CLIENT_ID ]]; then
  echo "앱 클라이언트 $CLIENT_NAME 이 없습니다. 먼저 ./setup-auth.sh 를 실행하세요." >&2
  exit 1
fi

echo "[Secrets Manager] $SOCIAL_SECRET_ID"
# 값은 변수에만 두고 출력하지 않는다. 파이썬에는 표준 입력으로만 넘긴다 (명령줄 인자에 남지 않게)
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$SOCIAL_SECRET_ID" --query SecretString --output text 2>/dev/null) || SECRET_JSON=""
if [[ -z $SECRET_JSON ]]; then
  echo "  - 없음 (도메인만 만들고 제공자 설정은 건너뛴다)"
fi

echo "[Cognito] 사용자 풀 도메인"
DOMAIN_PREFIX=$(aws cognito-idp describe-user-pool --user-pool-id "$POOL_ID" --query UserPool.Domain --output text)
if [[ $DOMAIN_PREFIX == None || -z $DOMAIN_PREFIX ]]; then
  DOMAIN_PREFIX=$COGNITO_DOMAIN_PREFIX
  aws cognito-idp create-user-pool-domain --user-pool-id "$POOL_ID" --domain "$DOMAIN_PREFIX" >/dev/null
  echo "  + $DOMAIN_PREFIX"
  for _ in $(seq 1 30); do
    STATUS=$(aws cognito-idp describe-user-pool-domain --domain "$DOMAIN_PREFIX" --query DomainDescription.Status --output text)
    [[ $STATUS == ACTIVE ]] && break
    sleep 5
  done
  echo "  = 상태 ${STATUS:-확인 못 함}"
else
  echo "  = $DOMAIN_PREFIX"
fi
COGNITO_DOMAIN=${DOMAIN_PREFIX}.auth.${AWS_REGION}.amazoncognito.com
IDP_RESPONSE=https://${COGNITO_DOMAIN}/oauth2/idpresponse

print_redirect() {
  echo
  echo "Google Cloud Console·Kakao Developers에 등록할 리디렉트 주소:"
  echo "  $IDP_RESPONSE"
}

# 비밀값 JSON(표준 입력)에서 제공자 하나를 골라 create/update-identity-provider 입력 파일을 만든다.
# 인자: 모드(create|update) 사용자풀ID 공개id 출력파일. 그 제공자가 비밀값에 없으면 종료 코드 3
IDP_PY='
import json, sys
mode, pool_id, pid, out = sys.argv[1:5]
try:
    cfg = json.loads(sys.stdin.read() or "{}").get(pid) or {}
except (json.JSONDecodeError, AttributeError):
    sys.exit(3)
cid, secret = cfg.get("clientId"), cfg.get("clientSecret")
if not cid or not secret:
    sys.exit(3)
if pid == "google":
    name, ptype = "Google", "Google"
    details = {"client_id": cid, "client_secret": secret, "authorize_scopes": "openid"}
else:
    name, ptype = "Kakao", "OIDC"
    details = {"client_id": cid, "client_secret": secret, "attributes_request_method": "GET",
               "oidc_issuer": "https://kauth.kakao.com", "authorize_scopes": "openid"}
req = {"UserPoolId": pool_id, "ProviderName": name, "ProviderDetails": details,
       # Cognito 사용자 이름만 제공자 sub로 잇는다. 이메일·이름·전화번호는 매핑하지 않는다
       "AttributeMapping": {"username": "sub"}}
if mode == "create":
    req["ProviderType"] = ptype
with open(out, "w") as f:
    json.dump(req, f)
print(name)
'

echo "[Cognito] 외부 로그인 제공자"
IDPS=()          # Cognito 제공자 이름 (Google, Kakao)
SOCIAL_PAIRS=()  # 공개id=Cognito 제공자 이름
for PID in google kakao; do
  NAME=$([[ $PID == google ]] && echo Google || echo Kakao)
  if aws cognito-idp describe-identity-provider --user-pool-id "$POOL_ID" --provider-name "$NAME" >/dev/null 2>&1; then
    MODE=update
  else
    MODE=create
  fi
  if ! printf '%s' "$SECRET_JSON" | python3 -c "$IDP_PY" "$MODE" "$POOL_ID" "$PID" "$TMP/idp-$PID.json" >/dev/null; then
    echo "  - $NAME: 비밀값에 없음, 건너뜀"
    continue
  fi
  aws cognito-idp "$MODE-identity-provider" --cli-input-json "file://$TMP/idp-$PID.json" >/dev/null
  rm -f "$TMP/idp-$PID.json"
  [[ $MODE == create ]] && echo "  + $NAME" || echo "  = $NAME"
  IDPS+=("$NAME")
  SOCIAL_PAIRS+=("$PID=$NAME")
done
unset SECRET_JSON

if [[ ${#IDPS[@]} -eq 0 ]]; then
  echo
  echo "설정된 제공자가 없어 앱 클라이언트·API 경로·Lambda 환경 변수는 바꾸지 않았다."
  echo "$SOCIAL_SECRET_ID 에 클라이언트 ID·비밀값을 넣고 다시 실행한다."
  print_redirect
  exit 0
fi

echo "[Cognito] 앱 클라이언트 $CLIENT_NAME (OAuth 인가 코드 + PKCE)"
WEB_DOMAIN=$(aws cloudfront list-distributions --query "DistributionList.Items[?Comment=='$DIST_COMMENT'].DomainName | [0]" --output text)
CALLBACKS=("$LOCAL_CALLBACK")
if [[ $WEB_DOMAIN == None || -z $WEB_DOMAIN ]]; then
  echo "  ! CloudFront 배포 $DIST_COMMENT 이 없어 로컬 주소만 등록한다 (setup-web.sh 후 다시 실행)"
else
  CALLBACKS=("https://$WEB_DOMAIN/login/callback/" "$LOCAL_CALLBACK")
fi
# update-user-pool-client는 넘기지 않은 값을 기본값으로 되돌린다.
# 그래서 지금 설정(인증 흐름, 토큰 유효 기간·단위, PreventUserExistenceErrors 등)을 읽어 전부 다시 넘기고 OAuth 값만 더한다.
# CLI 옵션으로 치면 --allowed-o-auth-flows code --allowed-o-auth-flows-user-pool-client --allowed-o-auth-scopes openid
#   --supported-identity-providers COGNITO {제공자} --callback-urls {주소} 와 같다
aws cognito-idp describe-user-pool-client --user-pool-id "$POOL_ID" --client-id "$CLIENT_ID" --output json \
  | python3 -c '
import json, sys
c = json.load(sys.stdin)["UserPoolClient"]
out, idps, callbacks = sys.argv[1], sys.argv[2].split(","), sys.argv[3:]
keep = ["UserPoolId", "ClientId", "ClientName", "RefreshTokenValidity", "AccessTokenValidity", "IdTokenValidity",
        "TokenValidityUnits", "ReadAttributes", "WriteAttributes", "ExplicitAuthFlows", "LogoutURLs", "DefaultRedirectURI",
        "AnalyticsConfiguration", "PreventUserExistenceErrors", "EnableTokenRevocation",
        "EnablePropagateAdditionalUserContextData", "AuthSessionValidity", "RefreshTokenRotation"]
req = {k: c[k] for k in keep if k in c}
def union(old, new):
    return list(dict.fromkeys((old or []) + new))
req["AllowedOAuthFlows"] = ["code"]
req["AllowedOAuthFlowsUserPoolClient"] = True
req["AllowedOAuthScopes"] = ["openid"]
req["SupportedIdentityProviders"] = union(c.get("SupportedIdentityProviders"), ["COGNITO"] + idps)
req["CallbackURLs"] = union(c.get("CallbackURLs"), callbacks)
with open(out, "w") as f:
    json.dump(req, f)
print("  인증 흐름 유지:", " ".join(req.get("ExplicitAuthFlows", [])))
print("  제공자:", " ".join(req["SupportedIdentityProviders"]))
print("  콜백:", " ".join(req["CallbackURLs"]))
' "$TMP/client.json" "$(IFS=,; echo "${IDPS[*]}")" "${CALLBACKS[@]}"
aws cognito-idp update-user-pool-client --cli-input-json "file://$TMP/client.json" >/dev/null
echo "  = 적용"

echo "[API Gateway] 공개 경로"
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='$API_NAME'].ApiId | [0]" --output text)
TARGET=$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='\$default'].Target | [0]" --output text)
for KEY in "GET /api/v1/auth/social/providers" "POST /api/v1/auth/social/start" "POST /api/v1/auth/social/token"; do
  RID=$(aws apigatewayv2 get-routes --api-id "$API_ID" --query "Items[?RouteKey=='$KEY'].RouteId | [0]" --output text)
  if [[ $RID == None || -z $RID ]]; then
    aws apigatewayv2 create-route --api-id "$API_ID" --route-key "$KEY" --target "$TARGET" --authorization-type NONE >/dev/null
    echo "  + 공개 경로: $KEY"
  else
    echo "  = 공개 경로: $KEY"
  fi
done

echo "[Lambda] COGNITO_DOMAIN, SOCIAL_PROVIDERS 환경 변수"
SOCIAL_PROVIDERS=$(IFS=,; echo "${SOCIAL_PAIRS[*]}")
CUR=$(aws lambda get-function-configuration --function-name "$FUNCTION_NAME" --query 'Environment.Variables' --output json)
NEW=$(echo "$CUR" | COGNITO_DOMAIN="$COGNITO_DOMAIN" SOCIAL_PROVIDERS="$SOCIAL_PROVIDERS" python3 -c '
import json, os, sys
d = json.load(sys.stdin) or {}
d["COGNITO_DOMAIN"] = os.environ["COGNITO_DOMAIN"]
d["SOCIAL_PROVIDERS"] = os.environ["SOCIAL_PROVIDERS"]
print(json.dumps({"Variables": d}))')
aws lambda update-function-configuration --function-name "$FUNCTION_NAME" --environment "$NEW" >/dev/null
aws lambda wait function-updated --function-name "$FUNCTION_NAME"
echo "  = 적용 (SOCIAL_PROVIDERS=$SOCIAL_PROVIDERS)"

print_redirect
echo
echo "확인: curl {API_BASE}/api/v1/auth/social/providers"
