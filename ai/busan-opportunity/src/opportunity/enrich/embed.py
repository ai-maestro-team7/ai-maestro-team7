"""임베딩 (B-02). "직무명 | 제목 | 업무 설명 | 필수 | 우대"를 벡터로 만들어 postings 인덱스에 넣는다.

필터 키는 isBusan, sido, jobMajor, active, deadline이다. title은 필터에 쓰지 않는다.
"""

from ..core import clock
from ..core.texts import posting_text
from ..deps import Deps
from ..models.posting import PostingLatest, PostingSnapshot, VectorMeta


def vector_meta(snapshot: PostingSnapshot, latest: PostingLatest) -> VectorMeta:
    return VectorMeta(
        is_busan=latest.is_busan,
        sido="" if latest.work_region.unknown else (latest.work_region.sido or ""),
        job_major=snapshot.job.major or "",
        active=not latest.is_expired,
        deadline=clock.deadline_number(snapshot.closes_at),
        title=snapshot.title,
    )


def embed_posting(deps: Deps, snapshot: PostingSnapshot, latest: PostingLatest) -> list[float]:
    """벡터를 만들어 넣고 돌려준다. 키는 jobPostingId라 다시 넣으면 덮어쓴다."""
    vector = deps.embedder.embed(posting_text(snapshot), kind="document")
    deps.vectors.put(snapshot.job_posting_id, vector, vector_meta(snapshot, latest).to_api())
    return vector
