"""공고 이름 색인 한 줄 (`POSTNAMES`, B-D08·B-D10). DynamoDB·메모리 저장소가 LATEST를 쓸 때 같은 규칙으로 만든다.

색인은 검색어·회사 이름 검색(맞춤 피드)과 로그인 없이 보는 공고 목록의 분류(지역, 기관 구분, 경력, 고용 형태)에 쓴다.
"""

from ..models.posting import PostingLatest, PostingName
from . import regions


def name_row(latest: PostingLatest) -> PostingName:
    """LATEST에서 색인 한 줄을 만든다. 해외 공고와 근무지를 모르는 공고는 시·도를 비운다."""
    overseas = latest.is_overseas or regions.is_overseas(latest.work_region)
    sido = None if overseas or latest.work_region.unknown else latest.work_region.sido
    return PostingName(job_posting_id=latest.job_posting_id, organization=latest.organization, title=latest.title,
                       job_name=latest.job.name, closes_at=latest.closes_at, org_type=latest.org_type, sido=sido,
                       is_overseas=overseas, career_type=latest.career_type, employment_type=latest.employment_type)
