from interview.bundles import make_bundles
from scoring_helpers import answer, session


def test_base_and_follow_up_grouped():
    s = session([answer("q1"), answer("q1", follow_up=True, text="꼬리 답변입니다."), answer("q2"), answer("q3")])
    bundles = make_bundles(s)
    assert [b.question_id for b in bundles] == ["q1", "q2", "q3"]
    assert bundles[0].follow_up.question_id == "q1-f" and bundles[1].follow_up is None
    assert all(b.evaluable for b in bundles)
    assert bundles[0].answer_text() == "저는 자료를 비교하고 대응표를 만들었습니다.\n꼬리 답변입니다."


def test_unevaluable_base_excluded():
    s = session([answer("q1", evaluable=False, reason="NO_ANSWER"), answer("q2"),
                 answer("q3", evaluable=False, reason="TRANSCRIBE_FAILED")])
    assert [b.evaluable for b in make_bundles(s)] == [False, True, False]


def test_unevaluable_follow_up_keeps_base_only():
    s = session([answer("q1"), answer("q1", follow_up=True, evaluable=False, reason="NO_ANSWER"), answer("q2"),
                 answer("q3")])
    b = make_bundles(s)[0]
    assert b.evaluable and [r.answer_id for r in b.answer_records()] == ["a-q1-1"]
    assert b.answer_text() == "저는 자료를 비교하고 대응표를 만들었습니다."


def test_unanswered_question_is_not_evaluable():
    s = session([answer("q1")])
    assert [b.evaluable for b in make_bundles(s)] == [True, False, False]
