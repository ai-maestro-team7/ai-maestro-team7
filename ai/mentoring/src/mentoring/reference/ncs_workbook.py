"""Read the NCS official workbook published by HRD Korea, scoped to the team's job profiles."""
import hashlib
import re
import ssl
import tempfile
from contextlib import closing
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

SITE = "https://www.ncs.go.kr"
LIBRARY = SITE + "/th06/bbs_lib_list.do?libDstinCd=01&searchKeyword=DB"
DETAIL = SITE + "/th06/bbs_lib_view.do?libDstinCd=01&libSeq="
DOWNLOAD = SITE + "/common/file/downloadFile.do"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


class OfficialLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.publications = []
        self.attachments = []
        self._attachment = None

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attr = dict(attrs)
        action = attr.get("onclick") or ""
        title = attr.get("title") or ""
        seq = re.search(r"fn_view\('(\d+)'\)", action)
        date = re.search(r"NCS\s*정보망\s*DB\s*\(대분류별,\s*(\d{4})년\s*(\d{1,2})월", title)
        if seq and date:
            year, month = map(int, date.groups())
            self.publications.append((f"{year:04d}-{month:02d}", seq[1]))
        file = re.search(r"gfn_file_downloadFile\('(\d+)'\s*,\s*'(\d+)'\s*,\s*'(\d+)'", action)
        self._attachment = file.groups() if file else None

    def handle_data(self, value):
        if self._attachment and "xlsx" in value.lower() and "정보망" in value:
            self.attachments.append(self._attachment)

    def handle_endtag(self, tag):
        if tag == "a":
            self._attachment = None


def open_ncs(request, timeout):
    # The NCS server offers RSA/AES-GCM on TLS 1.2. Keep hostname and CA checks.
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers("ECDHE+AESGCM:AES256-GCM-SHA384")
    return urlopen(request, timeout=timeout, context=context)


def links(url):
    with open_ncs(url, timeout=30) as response:
        doc = OfficialLinks()
        doc.feed(response.read().decode("utf-8"))
        return doc


def download(book, ids):
    form = dict(zip(("sysDstinCd", "fileMstky", "filedetlSeq"), ids))
    form["downlDstinCd"] = "09"
    request = Request(DOWNLOAD, data=urlencode(form).encode())
    digest = hashlib.sha256()
    with open_ncs(request, timeout=100) as response:
        while block := response.read(1024 * 1024):
            book.write(block)
            digest.update(block)
            if book.tell() > 400 * 1024 * 1024:
                raise ValueError("NCS 원장 크기가 임시 저장 공간 한도를 초과했습니다")
    book.seek(0)
    return digest.hexdigest()


def shared_strings(archive):
    strings = []
    with archive.open("xl/sharedStrings.xml") as stream:
        events = ET.iterparse(stream, events=("start", "end"))
        _, root = next(events)
        for event, elem in events:
            if event == "end" and elem.tag == NS + "si":
                strings.append("".join(t.text or "" for t in elem.iter(NS + "t")))
                root.clear()
    return strings


def sheet_rows(archive, path):
    with archive.open(path) as stream:
        events = ET.iterparse(stream, events=("start", "end"))
        sheet_data = None
        for event, elem in events:
            if event == "start" and elem.tag == NS + "sheetData":
                sheet_data = elem
            if event == "end" and elem.tag == NS + "row":
                yield elem
                sheet_data.clear()


def sheet_cells(row, strings):
    for cell in row:
        value = cell.findtext(NS + "v", "")
        if cell.get("t") == "s":
            value = strings[int(value)]
        yield cell.get("r").rstrip("0123456789"), value


def read_units(book, codes):
    # Stream selected worksheets. The full decompressed workbook is several GB.
    result = {code: {} for code in codes}
    categories = {code[:2] for code in codes}
    with ZipFile(book) as archive:
        strings = shared_strings(archive)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {rel.get("Id"): rel.get("Target") for rel in rels}
        for sheet in workbook.iter(NS + "sheet"):
            if sheet.get("name") not in categories:
                continue
            path = targets[sheet.get(REL)]
            path = path.lstrip("/") if path.startswith("/") else str(PurePosixPath("xl") / path)
            with closing(sheet_rows(archive, path)) as rows:
                cols = {v: k for k, v in sheet_cells(next(rows), strings)}
                unit_col, name_col, element_col = (cols[name] for name in ("능력단위분류번호", "능력단위명칭", "능력단위요소명"))
                for row in rows:
                    cells = dict(sheet_cells(row, strings))
                    unit = cells.get(unit_col, "").strip()
                    if unit[:8] not in result:
                        continue
                    name = cells[name_col].strip()
                    element = cells[element_col].strip()
                    if not name or not element:
                        raise ValueError("NCS 능력단위명 또는 요소명이 비어 있습니다")
                    entry = result[unit[:8]].setdefault(unit, {"name": name, "elements": set()})
                    entry["elements"].add(element)
    if not all(result.values()):
        raise ValueError("NCS 원장에서 일부 멘토링 직무 코드를 확인할 수 없습니다")
    return {code: [{"unitCode": unit, "name": value["name"], "elements": sorted(value["elements"])}
                   for unit, value in sorted(units.items())] for code, units in result.items()}


def collect_workbook(table, codes, now, save):
    date, seq = max(links(LIBRARY).publications)
    url = DETAIL + seq
    attachment, = links(url).attachments
    with tempfile.TemporaryFile() as book:
        digest = download(book, attachment)
        pending = []
        for code in codes:
            item = table.get_item(Key={"PK": f"NCS#{code}", "SK": "OFFICIAL#UNITS"},
                                  ConsistentRead=True).get("Item", {})
            if item.get("sha256") != digest or item.get("sourceUrl") != url:
                pending.append(code)
        if pending:
            by_code = read_units(book, pending)
            for code, units in by_code.items():
                save(table, {"PK": f"NCS#{code}", "SK": "OFFICIAL#UNITS", "entityType": "OfficialNcsUnits",
                             "units": units, "sourceUrl": url, "sourceReferenceMonth": date, "sha256": digest,
                             "collectedAt": now.isoformat()})
    return {"source": "ncs", "profiles": len(codes), "updated": len(pending), "sourceReferenceMonth": date}
