#!/usr/bin/env bash
# Lambda 실행 역할 team07-lambda-role 을 만들거나 정책을 갱신한다. (IAM 권한 필요)
# 정책 파일의 ${ACCOUNT_ID} 는 실행 시 현재 계정 ID로 채운다. 저장소에는 계정 ID를 적지 않는다.
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh
ROLE=${PREFIX}-lambda-role
POLICY=$(sed "s/\${ACCOUNT_ID}/$ACCOUNT_ID/g" iam/lambda-role-policy.json)

if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  echo "= $ROLE (이미 있음)"
else
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document file://iam/lambda-trust-policy.json \
    --tags Key=team,Value=$PREFIX >/dev/null
  echo "+ $ROLE"
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name ${PREFIX}-lambda-policy --policy-document "$POLICY"
echo "  정책 적용: $(aws iam get-role-policy --role-name "$ROLE" --policy-name ${PREFIX}-lambda-policy --query 'PolicyDocument.Statement[].Sid' --output text)"

# B 알림 일정용 역할: EventBridge Scheduler가 team07-api 를 부를 때 쓴다
if aws iam get-role --role-name "$SCHEDULER_ROLE_NAME" >/dev/null 2>&1; then
  echo "= $SCHEDULER_ROLE_NAME (이미 있음)"
else
  aws iam create-role --role-name "$SCHEDULER_ROLE_NAME" --assume-role-policy-document file://iam/scheduler-trust-policy.json \
    --tags Key=team,Value=$PREFIX >/dev/null
  echo "+ $SCHEDULER_ROLE_NAME"
fi
aws iam put-role-policy --role-name "$SCHEDULER_ROLE_NAME" --policy-name ${PREFIX}-scheduler-policy \
  --policy-document "$(sed "s/\${ACCOUNT_ID}/$ACCOUNT_ID/g" iam/scheduler-role-policy.json)"
