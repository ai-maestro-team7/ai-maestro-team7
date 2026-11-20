"""테스트 공용 설정. Bedrock·AWS는 부르지 않는다.

배포 묶음과 같은 import 이름을 쓰도록 저장소의 `ai/`(→ `interview`)와
`contracts/src/`(→ `team07_contracts`)를 sys.path 앞에 넣는다.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = REPO_ROOT / "ai" / "interview" / "samples"

for path in (REPO_ROOT / "ai", REPO_ROOT / "contracts" / "src"):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def sample_text(relative: str) -> str:
    return (SAMPLES_DIR / relative).read_text(encoding="utf-8")


def sample_json(relative: str):
    return json.loads(sample_text(relative))
