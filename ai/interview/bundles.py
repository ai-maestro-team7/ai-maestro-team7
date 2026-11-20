"""묶음 만들기 (report design §3, requirements 결정 4).

기본 질문 하나와 그 꼬리질문의 답변을 한 묶음으로 본다 (노션 6-①: 기본 + 꼬리를 한 묶음으로 평가).
- 기본 답변이 평가 불가면 그 묶음은 평가에서 뺀다 (이때는 꼬리질문이 없다, 1차 규칙)
- 꼬리 답변만 평가 불가면 기본 답변만으로 평가한다
"""

from dataclasses import dataclass

from .models import AnswerRecord, Question, Session


@dataclass(frozen=True)
class Bundle:
    question: Question
    base: AnswerRecord | None       # 아직 답하지 않았으면 None
    follow_up: AnswerRecord | None  # 꼬리질문이 없었으면 None

    @property
    def question_id(self) -> str:
        return self.question.question_id

    @property
    def evaluable(self) -> bool:
        return self.base is not None and self.base.evaluable

    def answer_records(self) -> list[AnswerRecord]:
        """평가에 쓰는 답변 (평가 가능한 기본·꼬리 답변)."""
        return [r for r in (self.base, self.follow_up) if r is not None and r.evaluable]

    def answer_text(self) -> str:
        """근거 인용 대조에 쓰는 답변 텍스트 (평가 가능한 답변을 줄바꿈으로 이음)."""
        return "\n".join(r.answer_text or "" for r in self.answer_records())


def make_bundles(session: Session) -> list[Bundle]:
    """session.questions 순서대로 묶음을 만든다. answers[]는 questionId(q1, q1-f)로 찾는다."""
    by_question: dict[str, AnswerRecord] = {}
    for record in session.answers:
        by_question.setdefault(record.question_id, record)  # 같은 질문에 답변은 하나 (1차 규칙)
    bundles = []
    for question in session.questions:
        base = by_question.get(question.question_id)
        follow_up = by_question.get(f"{question.question_id}-f")
        bundles.append(Bundle(question=question, base=base, follow_up=follow_up))
    return bundles
