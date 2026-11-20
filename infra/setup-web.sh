#!/usr/bin/env bash
# 프론트 화면 배포 자원 (S3 + CloudFront). 여러 번 실행해도 안전하다. 사람이 한 번 실행한다.
#  - 버킷 team07-web-<계정ID>: 퍼블릭 액세스 차단, CloudFront(OAC)만 읽을 수 있다
#  - CloudFront 함수 team07-web-index: `/jobs/` → `/jobs/index.html` (frontend/ 는 trailingSlash 정적 내보내기)
#  - 배포 team07-web (Comment로 찾는다): HTTPS로 넘김, 없는 경로는 /404.html
#  - 역할 team07-github-deploy 에 웹 버킷 쓰기·이 배포 캐시 무효화 권한을 따로 붙인다 (team07-github-deploy-web-policy)
# 끝나면 GitHub Secrets WEB_BUCKET, WEB_DISTRIBUTION_ID 에 넣을 값을 출력한다 (.github/workflows/frontend-deploy.yml).
set -euo pipefail
cd "$(dirname "$0")"
source ./config.sh

OAC_NAME=${PREFIX}-web-oac
FUNCTION_NAME_WEB=${PREFIX}-web-index
DIST_COMMENT=${PREFIX}-web
DEPLOY_ROLE=${PREFIX}-github-deploy
# AWS 관리형 캐시 정책 CachingOptimized (원본 Cache-Control을 따른다)
CACHE_POLICY_ID=658327ea-f89d-4fab-a63d-7e88639e58f6
TMP=$(mktemp -d)
trap 'rm -r "$TMP"' EXIT

# 1. 버킷
if aws s3api head-bucket --bucket "$WEB_BUCKET" >/dev/null 2>&1; then
  echo "= 버킷 $PREFIX-web-<계정ID> (이미 있음)"
else
  aws s3api create-bucket --bucket "$WEB_BUCKET" --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  echo "+ 버킷 $PREFIX-web-<계정ID>"
fi
aws s3api put-public-access-block --bucket "$WEB_BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-ownership-controls --bucket "$WEB_BUCKET" \
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
aws s3api put-bucket-tagging --bucket "$WEB_BUCKET" --tagging "TagSet=[{Key=team,Value=$PREFIX}]"

# 2. Origin Access Control
OAC_ID=$(aws cloudfront list-origin-access-controls \
  --query "OriginAccessControlList.Items[?Name=='$OAC_NAME'].Id | [0]" --output text)
if [ "$OAC_ID" = "None" ] || [ -z "$OAC_ID" ]; then
  OAC_ID=$(aws cloudfront create-origin-access-control --origin-access-control-config \
    "Name=$OAC_NAME,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3" \
    --query 'OriginAccessControl.Id' --output text)
  echo "+ OAC $OAC_NAME"
else
  echo "= OAC $OAC_NAME (이미 있음)"
fi

# 3. CloudFront 함수 (경로 → index.html)
if aws cloudfront describe-function --name "$FUNCTION_NAME_WEB" >/dev/null 2>&1; then
  ETAG=$(aws cloudfront describe-function --name "$FUNCTION_NAME_WEB" --stage DEVELOPMENT --query ETag --output text)
  ETAG=$(aws cloudfront update-function --name "$FUNCTION_NAME_WEB" --if-match "$ETAG" \
    --function-config "Comment=frontend index rewrite,Runtime=cloudfront-js-2.0" \
    --function-code fileb://web/index-rewrite.js --query ETag --output text)
  echo "= 함수 $FUNCTION_NAME_WEB (코드 갱신)"
else
  ETAG=$(aws cloudfront create-function --name "$FUNCTION_NAME_WEB" \
    --function-config "Comment=frontend index rewrite,Runtime=cloudfront-js-2.0" \
    --function-code fileb://web/index-rewrite.js --query ETag --output text)
  echo "+ 함수 $FUNCTION_NAME_WEB"
fi
aws cloudfront publish-function --name "$FUNCTION_NAME_WEB" --if-match "$ETAG" >/dev/null
FUNCTION_ARN=$(aws cloudfront describe-function --name "$FUNCTION_NAME_WEB" --stage LIVE \
  --query 'FunctionSummary.FunctionMetadata.FunctionARN' --output text)

# 4. 배포
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='$DIST_COMMENT'].Id | [0]" --output text)
if [ "$DIST_ID" = "None" ] || [ -z "$DIST_ID" ]; then
  cat > "$TMP/dist.json" <<JSON
{
  "DistributionConfig": {
    "CallerReference": "$DIST_COMMENT-$(date +%s)",
    "Comment": "$DIST_COMMENT",
    "Enabled": true,
    "DefaultRootObject": "index.html",
    "HttpVersion": "http2and3",
    "IsIPV6Enabled": true,
    "PriceClass": "PriceClass_200",
    "Origins": {
      "Quantity": 1,
      "Items": [{
        "Id": "web-s3",
        "DomainName": "$WEB_BUCKET.s3.$AWS_REGION.amazonaws.com",
        "OriginAccessControlId": "$OAC_ID",
        "S3OriginConfig": { "OriginAccessIdentity": "" }
      }]
    },
    "DefaultCacheBehavior": {
      "TargetOriginId": "web-s3",
      "ViewerProtocolPolicy": "redirect-to-https",
      "CachePolicyId": "$CACHE_POLICY_ID",
      "Compress": true,
      "AllowedMethods": {
        "Quantity": 2, "Items": ["GET", "HEAD"],
        "CachedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] }
      },
      "FunctionAssociations": {
        "Quantity": 1,
        "Items": [{ "FunctionARN": "$FUNCTION_ARN", "EventType": "viewer-request" }]
      }
    },
    "CustomErrorResponses": {
      "Quantity": 2,
      "Items": [
        { "ErrorCode": 403, "ResponsePagePath": "/404.html", "ResponseCode": "404", "ErrorCachingMinTTL": 10 },
        { "ErrorCode": 404, "ResponsePagePath": "/404.html", "ResponseCode": "404", "ErrorCachingMinTTL": 10 }
      ]
    }
  },
  "Tags": { "Items": [{ "Key": "team", "Value": "$PREFIX" }] }
}
JSON
  DIST_ID=$(aws cloudfront create-distribution-with-tags --distribution-config-with-tags "file://$TMP/dist.json" \
    --query 'Distribution.Id' --output text)
  echo "+ CloudFront 배포 $DIST_COMMENT (전파에 몇 분 걸림)"
else
  echo "= CloudFront 배포 $DIST_COMMENT (이미 있음, 설정은 바꾸지 않음)"
fi
DIST_ARN=arn:aws:cloudfront::${ACCOUNT_ID}:distribution/${DIST_ID}

# 5. 버킷 정책: 이 배포만 읽기
cat > "$TMP/bucket-policy.json" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowCloudFrontRead",
    "Effect": "Allow",
    "Principal": { "Service": "cloudfront.amazonaws.com" },
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::$WEB_BUCKET/*",
    "Condition": { "StringEquals": { "AWS:SourceArn": "$DIST_ARN" } }
  }]
}
JSON
aws s3api put-bucket-policy --bucket "$WEB_BUCKET" --policy "file://$TMP/bucket-policy.json"
echo "  버킷 정책: CloudFront 배포 $DIST_COMMENT 만 읽기"

# 6. 자동 배포 역할에 웹 배포 권한
if aws iam get-role --role-name "$DEPLOY_ROLE" >/dev/null 2>&1; then
  aws iam put-role-policy --role-name "$DEPLOY_ROLE" --policy-name ${PREFIX}-github-deploy-web-policy \
    --policy-document "$(sed -e "s/\${ACCOUNT_ID}/$ACCOUNT_ID/g" -e "s/\${WEB_BUCKET}/$WEB_BUCKET/g" \
      -e "s/\${DISTRIBUTION_ID}/$DIST_ID/g" iam/github-deploy-web-policy.json)"
  echo "  $DEPLOY_ROLE: 웹 버킷 쓰기 + 이 배포 캐시 무효화"
else
  echo "! $DEPLOY_ROLE 역할이 없어요. infra/setup-github-oidc.sh 를 먼저 실행한 뒤 이 스크립트를 다시 실행하세요."
fi

DOMAIN=$(aws cloudfront get-distribution --id "$DIST_ID" --query 'Distribution.DomainName' --output text)
echo
echo "화면 주소: https://$DOMAIN"
echo "GitHub Secrets 등록 (공개 저장소라 값은 채팅·문서에 남기지 않는다):"
echo "  gh secret set WEB_BUCKET --body \"$WEB_BUCKET\""
echo "  gh secret set WEB_DISTRIBUTION_ID --body \"$DIST_ID\""
echo "API CORS를 이 주소로 좁히려면: ALLOWED_ORIGIN=https://$DOMAIN infra/setup-api.sh"
