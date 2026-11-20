#!/usr/bin/env bash
# 코드만 바꿨을 때 쓰는 빠른 배포. (처음 한 번은 setup-api.sh)
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

ZIP=$(./package.sh)
aws lambda update-function-code --function-name "$FUNCTION_NAME" --zip-file "fileb://$ZIP" \
  --query '[FunctionName,LastModified,CodeSize]' --output text
aws lambda wait function-updated --function-name "$FUNCTION_NAME"
echo "배포 완료: $FUNCTION_NAME"
