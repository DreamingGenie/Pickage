"""백엔드 자바 소스에서 API 명세에 필요한 사실만 읽는다.

springdoc 이 만든 OpenAPI 는 응답 래퍼 ApiResponseBody<T> 의 T 를 지워 버려서 응답 필드가
비어 나온다. 그래서 응답·요청 필드는 DTO record 선언과 그 Javadoc @param 에서 직접 읽는다.
정규식 기반이라 record·enum·컨트롤러 매핑처럼 이 저장소가 쓰는 형태만 다룬다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Component:
    name: str
    type: str
    doc: str = ""
    raw_json: bool = False
    json_name: str | None = None


@dataclass
class RecordType:
    name: str
    qualified: str
    file: Path
    doc: str
    components: list[Component]


@dataclass
class EnumType:
    name: str
    qualified: str
    file: Path
    constants: list[str]


@dataclass
class Endpoint:
    method: str
    path: str
    java_method: str
    return_type: str
    summary: str = ""
    description: str = ""
    params: list[tuple[str, str, str, bool]] = field(default_factory=list)
    body_type: str | None = None


def clean_doc(text: str) -> str:
    text = re.sub(r"\{@(?:code|literal)\s+([^}]*)\}", r"`\1`", text)
    text = re.sub(r"\{@link(?:plain)?\s+([^}]*)\}", r"\1", text)
    text = re.sub(r"</?(?:b|p|i|em|strong|br|ul|li|pre)\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def javadoc_before(src: str, pos: int) -> str:
    """pos 바로 앞(어노테이션만 사이에 둔) Javadoc 본문을 돌려준다."""
    head = src[:pos]
    end = head.rfind("*/")
    if end < 0:
        return ""
    between = head[end + 2:]
    if re.sub(r"@\w+(\([^)]*\))?|\s", "", between):
        return ""
    start = head.rfind("/**", 0, end)
    if start < 0:
        return ""
    body = head[start + 3:end]
    return "\n".join(re.sub(r"^\s*\*\s?", "", line) for line in body.splitlines())


def param_docs(doc: str) -> dict[str, str]:
    out: dict[str, str] = {}
    cur = None
    for line in doc.splitlines():
        m = re.match(r"\s*@param\s+(\w+)\s*(.*)", line)
        if m:
            cur = m.group(1)
            out[cur] = m.group(2)
        elif re.match(r"\s*@\w+", line):
            cur = None
        elif cur:
            out[cur] += " " + line.strip()
    return {k: clean_doc(v) for k, v in out.items()}


def main_text(doc: str) -> str:
    lines = []
    for line in doc.splitlines():
        if re.match(r"\s*@\w+", line):
            break
        lines.append(line)
    text = clean_doc("\n".join(lines))
    # 첫 문단(첫 마침표까지)만 — 명세서에는 요지만 싣는다.
    return text


def split_top(s: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch in "<(":
            depth += 1
        elif ch in ">)":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def matching_paren(s: str, open_pos: int) -> int:
    depth = 0
    for i in range(open_pos, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced")


def strip_comments(src: str) -> str:
    """블록·줄 주석을 같은 길이의 공백으로 바꾼다(위치 유지)."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    src = re.sub(r"/\*.*?\*/", blank, src, flags=re.S)
    return re.sub(r"//[^\n]*", blank, src)


class JavaIndex:
    def __init__(self, root: Path):
        self.records: dict[str, list[RecordType]] = {}
        self.enums: dict[str, list[EnumType]] = {}
        self.by_file: dict[Path, dict[str, object]] = {}
        self.endpoints: list[Endpoint] = []
        for f in sorted(root.rglob("*.java")):
            self._parse(f)

    def _parse(self, f: Path):
        src = f.read_text(encoding="utf-8")
        code = strip_comments(src)
        local: dict[str, object] = {}
        outer = f.stem
        for m in re.finditer(r"\brecord\s+(\w+)\s*(?:<[^>{(]*>)?\s*\(", code):
            name = m.group(1)
            close = matching_paren(code, m.end() - 1)
            comps = []
            doc = javadoc_before(src, self._decl_start(src, m.start()))
            pdocs = param_docs(doc)
            for raw in split_top(code[m.end():close]):
                raw = raw.strip()
                if not raw:
                    continue
                anns = [(a.split(".")[-1], b) for a, b in re.findall(r"@([\w.]+)(?:\(([^)]*)\))?", raw)]
                bare = re.sub(r"@[\w.]+(\([^)]*\))?", "", raw).strip()
                bare = re.sub(r"\bfinal\s+", "", bare)
                typ, cname = bare.rsplit(None, 1)
                c = Component(cname, typ.strip(), pdocs.get(cname, ""))
                for an, arg in anns:
                    if an == "JsonRawValue":
                        c.raw_json = True
                    if an == "JsonProperty" and arg:
                        lit = re.search(r'"([^"]*)"', arg)
                        if lit:
                            c.json_name = lit.group(1)
                comps.append(c)
            rt = RecordType(name, name if name == outer else f"{outer}.{name}", f,
                            main_text(doc), comps)
            self.records.setdefault(name, []).append(rt)
            local[name] = rt
        for m in re.finditer(r"\benum\s+(\w+)\s*(?:implements[^{]*)?\{", code):
            body = code[m.end():]
            stop = re.search(r"[;}]", body)
            consts = [re.match(r"\s*(\w+)", c).group(1)
                      for c in split_top(body[:stop.start()]) if re.match(r"\s*\w+", c)]
            et = EnumType(m.group(1), m.group(1), f, consts)
            self.enums.setdefault(m.group(1), []).append(et)
            local[m.group(1)] = et
        self.by_file[f] = local
        if "@RestController" in code:
            self._parse_controller(f, src, code)

    @staticmethod
    def _decl_start(src: str, pos: int) -> int:
        """record 키워드 앞의 수식어·어노테이션을 건너뛴 선언 시작 위치."""
        line_start = src.rfind("\n", 0, pos) + 1
        i = line_start
        # 선언 위 어노테이션 줄들을 거슬러 올라간다
        while True:
            prev_end = i - 1
            if prev_end <= 0:
                break
            prev_start = src.rfind("\n", 0, prev_end) + 1
            if src[prev_start:prev_end].strip().startswith("@"):
                i = prev_start
            else:
                break
        return i

    def _parse_controller(self, f: Path, src: str, code: str):
        base = ""
        m = re.search(r"@RequestMapping\(\s*\"([^\"]*)\"", code)
        if m:
            base = m.group(1)
        for m in re.finditer(r"@(Get|Post|Put|Delete|Patch)Mapping\(([^)]*)\)", code):
            lit = re.search(r'"([^"]*)"', m.group(2))
            sub = lit.group(1) if lit else ""
            sig = re.search(r"public\s+(.+?)\s+(\w+)\s*\(", code[m.end():])
            open_pos = m.end() + sig.end() - 1
            close = matching_paren(code, open_pos)
            params, body = [], None
            for p in split_top(code[open_pos + 1:close]):
                pm = re.search(r"@(RequestParam|PathVariable)(?:\(([^)]*)\))?", p)
                if pm:
                    nm = re.search(r'name\s*=\s*"([^"]*)"', pm.group(2) or "") or \
                         re.search(r'"([^"]*)"', pm.group(2) or "")
                    bare = re.sub(r"@\w+(\([^)]*\))?", "", p).strip()
                    typ, var = bare.rsplit(None, 1)
                    req = pm.group(1) == "PathVariable" or "required = false" not in (pm.group(2) or "")
                    params.append((nm.group(1) if nm else var,
                                   "path" if pm.group(1) == "PathVariable" else "query", typ, req))
                elif "@RequestBody" in p:
                    bare = re.sub(r"@\w+(\([^)]*\))?", "", p).strip()
                    body = bare.rsplit(None, 1)[0]
            # @Operation 은 매핑 바로 앞에 있다
            window = src[max(0, m.start() - 3000):m.start()]
            op = window[window.rfind("@Operation("):] if "@Operation(" in window else ""
            summary = re.search(r'summary\s*=\s*"([^"]*)"', op)
            desc_m = re.search(r"description\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)", op)
            desc = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', desc_m.group(1))) if desc_m else ""
            self.endpoints.append(Endpoint(
                m.group(1).upper(), base + sub, sig.group(2), sig.group(1).strip(),
                summary.group(1) if summary else "", desc, params, body))

    # ── 타입 해석 ─────────────────────────────────────────────────────

    def resolve(self, name: str, ctx: Path | None):
        name = name.split(".")[-1]
        if ctx and name in self.by_file.get(ctx, {}):
            return self.by_file[ctx][name]
        for table in (self.records, self.enums):
            if name in table and len(table[name]) == 1:
                return table[name][0]
        return None
