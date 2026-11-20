from unittest.mock import patch

import pytest

from mentoring.reference.collection import exam_rows
from mentoring.reference.ncs_workbook import OfficialLinks


def test_exam_pages_are_complete_before_cache_replacement():
    row = {"implYy": "2026"}
    pages = [{"totalCount": 2, "pageNo": 1, "items": [row]}, {"totalCount": 2, "pageNo": 2, "items": [row]}]
    with patch("mentoring.reference.collection.exam_page", side_effect=pages):
        assert exam_rows("key", "G541", 2026) == [row, row]
    pages[1]["items"] = []
    with patch("mentoring.reference.collection.exam_page", side_effect=pages), pytest.raises(ValueError):
        exam_rows("key", "G541", 2026)


def test_only_official_workbook_posts_and_xlsx_are_selected():
    parser = OfficialLinks()
    parser.feed("""<a onclick="fn_view('123')" title="NCS 정보망 DB(대분류별, 2026년 2월 기준)">DB</a>
        <a onclick="fn_view('999')" title="기타 자료">기타</a>
        <a onclick="gfn_file_downloadFile('01','2','3', {})"><span>첨부파일</span>NCS정보망DB.xlsx</a>""")
    assert parser.publications == [("2026-02", "123")]
    assert parser.attachments == [("01", "2", "3")]
