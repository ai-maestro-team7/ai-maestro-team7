#!/usr/bin/env bash
# GitHub Actions 자동 배포용 (OIDC, 액세스 키 없음). 여러 번 실행해도 안전하다.
#  - 신원 제공자 token.actions.githubusercontent.com (계정에 하나. 있으면 그대로 씀)
#  - 역할 team07-github-deploy: 이 저장소 main 브랜치의 작업만 받을 수 있고, team07-api 코드 갱신만 할 수 있다
#    (이 저장소는 GitHub "immutable subject"를 써서 sub에 소유자·저장소 숫자 ID가 붙는다. 두 형식 모두 허용)
#  - IAM·환경 변수·API 설정 변경은 자동 배포에 넣지 않는다 (setup-role.sh, setup-api.sh는 사람이 실행)
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
ROLE=${PREFIX}-github-deploy
PROVIDER=arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com

if aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$PROVIDER" >/dev/null 2>&1; then
  echo "= OIDC 신원 제공자 (이미 있음)"
else
  aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
  echo "+ OIDC 신원 제공자"
fi

TRUST=$(sed "s/\${ACCOUNT_ID}/$ACCOUNT_ID/g" iam/github-deploy-trust-policy.json)
if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam update-assume-role-policy --role-name "$ROLE" --policy-document "$TRUST"
  echo "= $ROLE (신뢰 정책 갱신)"
else
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document "$TRUST" --max-session-duration 3600 \
    --tags Key=team,Value=$PREFIX >/dev/null
  echo "+ $ROLE"
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name ${PREFIX}-github-deploy-policy \
  --policy-document "$(sed "s/\${ACCOUNT_ID}/$ACCOUNT_ID/g" iam/github-deploy-policy.json)"
echo "  정책: team07-api 코드 갱신만"
echo
echo "GitHub 저장소 Secret AWS_DEPLOY_ROLE_ARN 에 넣을 값: arn:aws:iam::<계정ID>:role/$ROLE"
