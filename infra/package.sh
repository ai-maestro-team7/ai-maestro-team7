#!/usr/bin/env bash
# backend/ 를 Lambda용 zip으로 묶고 zip 경로를 출력한다.
# backend/requirements.txt 가 있으면 Lambda(arm64, Python 3.13)용으로 의존성을 같이 넣는다.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BUILD=$ROOT/build/lambda
ZIP=$ROOT/build/function.zip

rm -rf "$BUILD" "$ZIP"
mkdir -p "$BUILD"
find "$ROOT/backend" -maxdepth 1 -name '*.py' ! -name 'test_*' -exec cp {} "$BUILD"/ \;

# 모의면접 함수 패키지 (C, 저장소의 ai/interview/). 파이썬 파일이 있으면 `interview` 패키지로 넣는다
# → backend/interview_api.py가 대역(interview_stub) 대신 이걸 쓴다
if compgen -G "$ROOT/ai/interview/*.py" >/dev/null; then
  rsync -a --exclude '__pycache__' --exclude 'tests' --exclude 'samples' --exclude '.gitkeep' "$ROOT/ai/interview/" "$BUILD/interview/"
fi

# 부산 기회 추천 (B, ai/busan-opportunity/src/opportunity/) → `opportunity` 패키지
if compgen -G "$ROOT/ai/busan-opportunity/src/opportunity/*.py" >/dev/null; then
  rsync -a --exclude '__pycache__' "$ROOT/ai/busan-opportunity/src/opportunity/" "$BUILD/opportunity/"
fi

# 멘토링 (A, ai/mentoring/src/mentoring/) → `mentoring` 패키지
if compgen -G "$ROOT/ai/mentoring/src/mentoring/*.py" >/dev/null; then
  rsync -a --exclude '__pycache__' "$ROOT/ai/mentoring/src/mentoring/" "$BUILD/mentoring/"
fi

# 채팅 Agent (D-38, ai/supervisor/src/supervisor/) → `supervisor` 패키지
if compgen -G "$ROOT/ai/supervisor/src/supervisor/*.py" >/dev/null; then
  rsync -a --exclude '__pycache__' "$ROOT/ai/supervisor/src/supervisor/" "$BUILD/supervisor/"
fi

# 파트 간 계약 패키지 (contracts/src/team07_contracts/, D-18) → `team07_contracts`
if [[ -d $ROOT/contracts/src/team07_contracts ]]; then
  rsync -a --exclude '__pycache__' --exclude 'testing' "$ROOT/contracts/src/team07_contracts/" "$BUILD/team07_contracts/"
fi

for req in "$ROOT/backend/requirements.txt" "$ROOT/ai/interview/requirements.txt" \
           "$ROOT/ai/busan-opportunity/requirements.txt" "$ROOT/ai/mentoring/requirements.txt" \
           "$ROOT/ai/supervisor/requirements.txt" \
           "$ROOT/contracts/requirements.txt"; do
  if [[ -s $req ]]; then
    uv pip install --quiet -r "$req" --target "$BUILD" \
      --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary=:all: >&2
  fi
done

(cd "$BUILD" && zip -qr "$ZIP" . -x '__pycache__/*' '*.pyc')
echo "$ZIP"
