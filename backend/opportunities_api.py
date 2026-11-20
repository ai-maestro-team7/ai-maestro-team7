"""부산 기회 추천 백엔드 연결 — /api/v1/opportunities/*

역할 분담 (B 개발명세서 §5, docs/api.md §6):
  백엔드(여기) = 사용자 확인, 공통 함수(지원 자격 판정·워크스페이스)와 AWS 저장소를 묶어 B 함수에 넘기기
  B 함수(저장소 ai/busan-opportunity/ → 배포 때 `opportunity` 패키지, 담당 박상원) = 추천·비교·정책·알림 규칙

입구 세 개가 같은 B 함수를 부른다:
  handle        REST (API Gateway HTTP API)
  handle_agent  통합 Agent의 Action Group `BusanOpportunity` (userId는 sessionAttributes에서만 읽음)
  run_schedule  EventBridge Scheduler 일회성 일정 (마감 D-7·D-3, 정책 열림)
"""

import eligibility
import workspace
from common import TeamError, error_response, get_user_id, new_request_id

try:  # 실제 B 코드 (infra/package.sh가 `opportunity`로 묶음)
    from opportunity.api import agent_handler, rest_handler
    from opportunity.notify import notifier
    from opportunity.store.factory import build_aws_deps

    IMPL_NAME = "opportunity"
except ImportError:  # 배포 묶음에 없으면 해당 경로만 501
    IMPL_NAME = None

_deps = None


class Workspaces:
    """B가 쓰는 워크스페이스 창구. 지원 상태는 워크스페이스에만 둔다 (D-36)."""

    def workspace_id(self, job_posting_id):
        return workspace.workspace_id(job_posting_id=job_posting_id)

    def put_tx_item(self, user_id, job_posting_id, snapshot_id, status):
        """`OPP#SAVED#`와 한 트랜잭션으로 쓸 항목. 이미 있으면 None."""
        try:
            workspace.get_workspace(user_id, self.workspace_id(job_posting_id))
            return None
        except TeamError as e:
            if e.code != "WORKSPACE_NOT_FOUND":
                raise
        return workspace.workspace_put(user_id, job_posting_id=job_posting_id, snapshot_id=snapshot_id, status=status)

    def get_status(self, user_id, workspace_id):
        try:
            return workspace.get_workspace(user_id, workspace_id).get("status")
        except TeamError:
            return None

    def set_status(self, user_id, workspace_id, status):
        workspace.set_status(user_id, workspace_id, status)


def deps():
    """Lambda 컨테이너마다 한 번만 만든다 (boto3 클라이언트 재사용)."""
    global _deps
    if _deps is None:
        _deps = build_aws_deps(eligibility=eligibility.evaluate_eligibility, workspaces=Workspaces())
    return _deps


def not_implemented():
    return error_response(TeamError(501, "NOT_IMPLEMENTED", "아직 연결되지 않은 기능이에요.", False), new_request_id())


def handle(event, method, path):
    if IMPL_NAME is None:
        return not_implemented()
    try:
        user_id = get_user_id(event)
    except TeamError as e:
        return error_response(e, new_request_id())
    return rest_handler.handle(event, deps(), user_id)


def handle_agent(event):
    return agent_handler.handle(event, deps())


def run_schedule(event):
    return {"notified": notifier.handle_schedule(deps(), event["oppSchedule"])}
