"""턴마다 모델에 넘기는 사용자 문맥 (개발계획서4 §5.1).

이력서·자소서·경험 블록에서 A가 정리한 요약과 기본 프로필 일부를 `<user_context>` 데이터로 붙인다.
원문·인용문·연락처·나이·소득은 넣지 않는다 (A F-06 "이력서 전문 대신 근거 요약", 제품 원칙 7).
도구를 한 번 덜 부르게 해서 답이 빨라지고, 모델이 매번 사용자 경험을 보고 답하게 한다.
"""

import json

from .tools import TurnTools

# 기본 프로필에서 문맥에 넣는 항목. 나이·거주지·소득은 정책 판정 도구가 직접 읽으므로 넣지 않는다
PROFILE_KEYS = ("desiredJobs", "desiredRegion", "desiredSalaryMin", "desiredCareerType", "major", "educationLevel",
                "graduationStatus", "employmentStatus", "careerYears")


POSTING_KEYS = ("jobPostingId", "title", "organization", "workRegion", "isSample")


def build_user_context(tools: TurnTools) -> dict:
    saved = tools.saved_profile()
    profile = {k: saved[k] for k in PROFILE_KEYS if saved.get(k) not in (None, "", [])}
    if "desiredJobs" in profile:
        profile["desiredJobs"] = [j.get("name") for j in profile["desiredJobs"] if isinstance(j, dict) and j.get("name")]
    docs = tools.documents()
    summary = tools.deps.docs.career_summary(tools.user_id) or {}
    return {
        "basicProfile": profile,
        "documents": [{"documentType": d.document_type, "title": d.title, "status": d.status} for d in docs],
        "attachedThisMessage": [d.document_type for d in docs if d.document_id in tools.attachments],
        "hasCoverLetter": tools.cover_letter() is not None,
        "careerProfile": summary,
        # 바로 앞 답에서 보여 준 공고. "이 공고", "첫 번째 공고"가 무엇인지 알 수 있게 한다
        "recentPostings": [{k: p[k] for k in POSTING_KEYS if k in p}
                           for p in tools.recent_postings[:tools.deps.config.recent_postings]],
    }


def context_block(context: dict) -> str:
    """모델 메시지 앞에 붙일 글. 태그 안은 데이터일 뿐 지시가 아니다 (프롬프트 인젝션 방어)."""
    return "<user_context>\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":")) + "\n</user_context>"
