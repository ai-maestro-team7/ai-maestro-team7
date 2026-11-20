"""임베딩에 넣는 글. 공고와 프로필이 같은 방식으로 만들어져야 유사도를 비교할 수 있다."""

from ..models.enums import RequirementKind
from ..models.posting import PostingSnapshot
from ..models.profile import BasicProfile


def posting_text(snapshot: PostingSnapshot) -> str:
    """"직무명 | 제목 | 업무 설명 | 필수 | 우대" (개발계획서2 B-02)."""
    required = ", ".join(r.name for r in snapshot.requirements if r.kind == RequirementKind.REQUIRED_SKILL)
    preferred = ", ".join(r.name for r in snapshot.requirements if r.kind == RequirementKind.PREFERRED_SKILL)
    parts = [snapshot.job.name, snapshot.title, snapshot.job_description or "", required, preferred]
    return " | ".join(part.strip() for part in parts)


def profile_text(profile: BasicProfile) -> str:
    """희망 직무·전공·기술 (B-03). 이름이나 연락처 같은 개인정보는 넣지 않는다."""
    jobs = ", ".join(job.name for job in profile.desired_jobs)
    parts = [jobs, profile.major or "", ", ".join(profile.skills), ", ".join(profile.certificates)]
    return " | ".join(part.strip() for part in parts)
