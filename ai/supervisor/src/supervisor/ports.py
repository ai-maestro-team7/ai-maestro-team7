"""Agent 패키지가 바깥에 기대는 것들 (개발계획서4 §3). 구현은 백엔드(`backend/agent_api.py`)가 넣는다.

이 패키지는 `backend/`도 다른 파트 패키지도 import하지 않는다 (공통 스펙 Requirement 12).
모든 메서드는 백엔드가 토큰에서 확인한 user_id를 받는다. 모델이 고른 값으로 사용자를 바꾸지 않는다.
"""

from collections.abc import Callable
from typing import Any, Protocol

from .models import ChatMessage, ChatReply, ChatSession, DocumentInfo


class ChatStore(Protocol):
    """`team07-career-mentor`의 `SESSION#`·`CHAT#` (db-schema §2.1). Scan 없이 GetItem·Query만 쓴다."""

    def get_session(self, user_id: str, session_id: str) -> ChatSession | None: ...

    def create_session(self, session: ChatSession) -> None: ...

    def begin_turn(self, user_id: str, session_id: str, message_id: str, *, now: str, stale_before: str,
                   max_messages: int) -> bool:
        """진행 중인 턴이 없거나 stale_before보다 오래됐고, 메시지 수가 한도 안이면 이 턴을 잡고 True."""
        ...

    def end_turn(self, user_id: str, session_id: str, message_id: str, *, now: str) -> None:
        """이 턴이 잡고 있을 때만 풀어 준다."""
        ...

    def put_message(self, message: ChatMessage) -> None: ...

    def get_message(self, user_id: str, session_id: str, message_id: str) -> ChatMessage | None: ...

    def list_messages(self, user_id: str, session_id: str, limit: int) -> list[ChatMessage]:
        """오래된 순."""
        ...

    def claim_message(self, user_id: str, session_id: str, message_id: str, *, now: str) -> bool:
        """PENDING → PROCESSING 조건부 전이. 바꿨으면 True (같은 작업이 두 번 와도 한 번만 돈다)."""
        ...

    def finish_message(self, message: ChatMessage) -> bool:
        """실행이 잡은(PROCESSING) 답만 결과로 바꾼다. 그사이 멈췄거나 지운 답이면 False (늦은 결과는 버린다)."""
        ...

    def cancel_message(self, user_id: str, session_id: str, message_id: str, *, now: str) -> bool:
        """만드는 중(PENDING·PROCESSING)인 답을 CANCELLED로 바꾼다. 이미 끝난 답이면 False."""
        ...

    def list_sessions(self, user_id: str) -> list[ChatSession]:
        """내 대화 전부 (`SESSION#` Query). 순서는 서비스가 정한다."""
        ...

    def set_pinned(self, user_id: str, session_id: str, pinned: bool) -> bool:
        """대화 고정을 바꾼다. 없는 대화면 False."""
        ...

    def delete_session(self, user_id: str, session_id: str) -> bool:
        """대화와 그 메시지를 모두 지운다. 없는 대화면 False."""
        ...


class OpportunityPort(Protocol):
    """B 함수 (`opportunity.api.agent_handler`). 응답은 B Agent 응답의 카멜 dict 그대로다."""

    def search_postings(self, user_id: str, *, job_name: str | None, keyword: str | None, organization: str | None,
                        region: str | None, min_salary: int | None, career_type: str | None,
                        query_terms: list[str] | None, scope: str) -> dict:
        """scope: OFFICIAL(공공 API로 모은 공고) 또는 TEAM(팀이 넣어 둔 공고)."""
        ...

    def find_companies(self, user_id: str, name: str) -> list[dict]:
        """회사 이름으로 우리 기업 데이터(부산 청끌·강소·이전기관). 회사 정보만, 출처·기준일 포함."""
        ...

    def match_policies(self, user_id: str, *, stage: str | None) -> dict: ...

    def ask_policies(self, user_id: str, question: str) -> dict: ...

    def profile_region_code(self, region: str | None) -> str | None:
        """지역 말을 기본 프로필 `desiredRegion` 값(시·도 코드 또는 ALL)으로. 코드 하나로 못 적으면 None."""
        ...


class CareerDocsPort(Protocol):
    """A 문서·역량 프로필 (읽기만)."""

    def latest_documents(self, user_id: str) -> list[DocumentInfo]: ...

    def resume_terms(self, user_id: str) -> list[str]:
        """최신 역량 프로필의 역량 이름 (확인 전 포함, 부족으로 확인한 것은 뺌). 없으면 빈 목록."""
        ...

    def career_summary(self, user_id: str) -> dict:
        """이력서·자소서·경험 블록 요약 (개발계획서4 §5.1). 원문·인용문·연락처는 넣지 않는다. 없으면 빈 dict.

        {skills[{name, confirmed, evidence}], projects[{name, summary, period}], experiences[…], certificates[],
         needsConfirmation[], stories[{title, situation, result, learning}]}
        """
        ...


class ProfilePort(Protocol):
    def get_basic_profile(self, user_id: str) -> dict | None:
        """`PROFILE#BASIC` (카멜 키). 없으면 None."""
        ...

    def update_basic_profile(self, user_id: str, patch: dict) -> dict:
        """보낸 항목만 바꾼다 (`PUT /api/v1/me/profile`과 같은 검사). 바뀐 프로필을 돌려준다."""
        ...


class AgentRunner(Protocol):
    def run(self, *, system_prompt: str, history: list[dict], message: str, tools: list[Callable[..., Any]],
            max_turns: int) -> ChatReply:
        """history = [{"role": "user"|"assistant", "text": …}] (user로 시작, 번갈아). 스키마를 못 맞추면 OutputInvalid."""
        ...


class Dispatcher(Protocol):
    def dispatch(self, event: dict) -> None:
        """턴 실행 이벤트 보내기. 운영은 Lambda 비동기 자기 호출 (D-19)."""
        ...
