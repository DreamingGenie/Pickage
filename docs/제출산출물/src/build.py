"""제출 산출물(ERD · 시스템 아키텍처 · API 명세서) PDF 생성기.

    python docs/제출산출물/src/build.py            # HTML 생성 + PDF 변환
    python docs/제출산출물/src/build.py --html     # HTML 만 (PDF 변환 생략)

입력은 모두 저장소 안에 있다 — 네트워크·DB 없이 다시 돌릴 수 있다.
  * src/data/schema.json          Flyway V1~V13 을 적용한 빈 DB 에서 뽑은 스키마 (refresh_inputs.sh)
  * src/data/backend-openapi.json springdoc /v3/api-docs (refresh_inputs.sh)
  * src/data/rag-openapi.json     ai/rag FastAPI 앱의 openapi() (refresh_inputs.sh)
  * backend/src/main/java         DTO record·컨트롤러 (응답 필드·운영자 API)
  * src/notes.py                  원본에 설명이 없는 자리만 사람이 채운 것
  * src/architecture.html         시스템 아키텍처 (손으로 그린 SVG)

PDF 는 Chrome headless 로 찍는다. 경로가 다르면 CHROME 환경변수로 지정한다.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
BUILD = OUT / "build"
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

import notes  # noqa: E402
from javasrc import JavaIndex, RecordType, EnumType  # noqa: E402

TODAY = date.today().isoformat()
esc = html.escape


def git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def read_css() -> str:
    return (HERE / "style.css").read_text(encoding="utf-8")


def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{esc(title)}</title>
<style>{read_css()}</style></head><body>{body}</body></html>"""


def md_inline(text: str) -> str:
    """`code` 만 살린다."""
    parts = re.split(r"`([^`]*)`", text)
    return "".join(f"<code>{esc(p)}</code>" if i % 2 else esc(p) for i, p in enumerate(parts))


def short(text: str, limit: int = 170) -> str:
    """설명을 명세서 분량으로 줄인다 — 앞 문장부터 채워 limit 근처에서 끊는다."""
    text = re.sub(r"^\s*\d+(\.\d+)+\s*—\s*", "", text)
    text = re.sub(r"\s*\((?:명세\s*)?(?:§[\d.]+|\d+\.\d+)[^)]*\)", "", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\s+([.,])", r"\1", text)
    text = re.sub(r"#(\w)", r"\1", text)
    sentences = re.split(r"(?<=[다요음함.])\.\s+|(?<=다\.)\s+|(?<=\.)\s+(?=[A-Z가-힣`(])", text)
    out = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        cand = (out + " " + s).strip() if out else s
        if out and len(cand) > limit:
            break
        out = cand
        if len(out) > limit * 0.6:
            break
    if len(out) > limit + 60:
        out = out[:limit].rstrip() + "…"
    return out


# ══ ERD ═══════════════════════════════════════════════════════════════

W, HEAD, ROW, GAP, COLSTEP, TOP = 300, 30, 17, 36, 370, 20


def short_type(t: str) -> str:
    t = t.replace("character varying", "varchar").replace("timestamp with time zone", "timestamptz")
    t = t.replace("timestamp without time zone", "timestamp").replace("double precision", "float8")
    return t


def parse_fk(defn: str):
    m = re.match(r"FOREIGN KEY \(([^)]*)\) REFERENCES (\w+)\(([^)]*)\)", defn)
    cols = [c.strip() for c in m.group(1).split(",")]
    ref = [c.strip() for c in m.group(3).split(",")]
    return cols, m.group(2), ref


def pk_cols(t) -> list[str]:
    for c in t["constraints"] or []:
        if c["type"] == "p":
            return [x.strip() for x in re.search(r"\(([^)]*)\)", c["def"]).group(1).split(",")]
    return []


def fk_list(t):
    return [(c["name"], *parse_fk(c["def"]), c["def"]) for c in t["constraints"] or [] if c["type"] == "f"]


def bold(text: str) -> str:
    parts = re.split(r"\*\*([^*]+)\*\*", text)
    return "".join(f"<b>{esc(p)}</b>" if i % 2 else esc(p) for i, p in enumerate(parts))


def col_desc(table: str, col: dict) -> str:
    return col["comment"] or notes.COLUMNS.get((table, col["name"]), "")


def erd_svg(schema: dict) -> str:
    tables = {t["table"]: t for t in schema}
    missing = set(tables) ^ {n for col in notes.LAYOUT for n in col}
    if missing:
        raise SystemExit(f"notes.LAYOUT 과 스키마의 테이블이 다르다: {sorted(missing)}")
    box = {}
    for ci, colnames in enumerate(notes.LAYOUT):
        heights = [HEAD + ROW * len(tables[n]["columns"]) + 6 for n in colnames]
        y = TOP + 44
        if ci == 1:  # package 를 왼쪽 열의 가운데쯤에 둔다
            y += 30
        for n, h in zip(colnames, heights):
            box[n] = (20 + ci * COLSTEP, y, h, ci)
            y += h + (GAP + 34 if ci == 1 else GAP)
    height = max(y + h for (_, y, h, _) in box.values()) + 30
    width = 20 + (len(notes.LAYOUT) - 1) * COLSTEP + W + 90

    out = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" class="erd">']
    # 범례
    lx = 20
    for key, (label, color) in notes.GROUPS.items():
        out.append(f'<rect x="{lx}" y="{TOP}" width="14" height="14" rx="3" fill="{color}"/>'
                   f'<text x="{lx + 20}" y="{TOP + 12}" class="legend">{esc(label)}</text>')
        lx += 40 + len(label) * 12
    out.append(f'<g transform="translate({lx + 10},{TOP})">'
               f'<rect x="0" y="0" width="22" height="14" rx="3" class="pk"/><text x="11" y="11" class="badge">PK</text>'
               f'<text x="28" y="12" class="legend">기본 키</text>'
               f'<rect x="90" y="0" width="22" height="14" rx="3" class="fk"/><text x="101" y="11" class="badge">FK</text>'
               f'<text x="118" y="12" class="legend">외래 키</text>'
               f'<path d="M200 7 H250" class="rel"/><path d="M200 1 L208 7 L200 13" class="rel"/>'
               f'<path d="M244 1 V13 M248 1 V13" class="rel"/>'
               f'<text x="258" y="12" class="legend">N : 1 (까마귀발 = 참조하는 쪽 여러 행)</text></g>')

    def anchor(n, colname):
        x, y, h, ci = box[n]
        names = [c["name"] for c in tables[n]["columns"]]
        return y + HEAD + ROW * names.index(colname) + ROW / 2

    same_col_bulge: dict[str, int] = {}
    edges = []
    for n, t in tables.items():
        for _, cols, ref_t, ref_cols, _ in fk_list(t):
            edges.append((n, cols[0], ref_t, ref_cols[0]))
    for src, scol, dst, dcol in edges:
        sx, _, _, sci = box[src]
        dx_, _, _, dci = box[dst]
        y1, y2 = anchor(src, scol), anchor(dst, dcol)
        if src == dst:
            x = sx + W
            d = f"M{x} {y1} C{x + 50} {y1}, {x + 50} {y2}, {x} {y2}"
            ends = ((x, y1, 1), (x, y2, 1))
        elif sci == dci:
            k = same_col_bulge.get(str(sci), 0)
            same_col_bulge[str(sci)] = k + 1
            x = sx + W
            b = 46 + 16 * k
            d = f"M{x} {y1} C{x + b} {y1}, {x + b} {y2}, {x} {y2}"
            ends = ((x, y1, 1), (x, y2, 1))
        elif sci < dci:
            x1, x2 = sx + W, dx_
            m = (x2 - x1) / 2
            d = f"M{x1} {y1} C{x1 + m} {y1}, {x2 - m} {y2}, {x2} {y2}"
            ends = ((x1, y1, 1), (x2, y2, -1))
        else:
            x1, x2 = sx, dx_ + W
            m = (x1 - x2) / 2
            d = f"M{x1} {y1} C{x1 - m} {y1}, {x2 + m} {y2}, {x2} {y2}"
            ends = ((x1, y1, -1), (x2, y2, 1))
        out.append(f'<path d="{d}" class="rel"/>')
        (ax, ay, adir), (bx, by, bdir) = ends
        # 참조하는 쪽: 까마귀발, 참조되는 쪽: 두 줄
        out.append(f'<path d="M{ax + 12 * adir} {ay} L{ax} {ay - 6} M{ax + 12 * adir} {ay} L{ax} {ay + 6}" class="rel"/>')
        out.append(f'<path d="M{bx + 6 * bdir} {by - 6} V{by + 6} M{bx + 10 * bdir} {by - 6} V{by + 6}" class="rel"/>')

    for n, (x, y, h, _) in box.items():
        t = tables[n]
        group = notes.TABLES[n][0]
        color = notes.GROUPS[group][1]
        pks = set(pk_cols(t))
        fks = {c for _, cols, *_ in fk_list(t) for c in cols}
        out.append(f'<g class="tbl"><rect x="{x}" y="{y}" width="{W}" height="{h}" rx="6" class="box"/>'
                   f'<path d="M{x} {y + 6} a6 6 0 0 1 6 -6 h{W - 12} a6 6 0 0 1 6 6 v{HEAD - 6} h-{W} z" fill="{color}"/>'
                   f'<text x="{x + 10}" y="{y + 20}" class="tname">{esc(n)}</text>')
        if t["partkey"]:
            out.append(f'<text x="{x + W - 10}" y="{y + 20}" class="tnote" text-anchor="end">파티션</text>')
        for i, c in enumerate(t["columns"]):
            ry = y + HEAD + ROW * i
            if i % 2:
                out.append(f'<rect x="{x + 1}" y="{ry}" width="{W - 2}" height="{ROW}" class="zebra"/>')
            bx = x + 6
            if c["name"] in pks:
                out.append(f'<rect x="{bx}" y="{ry + 3}" width="20" height="11" rx="2" class="pk"/><text x="{bx + 10}" y="{ry + 12}" class="badge">PK</text>')
            if c["name"] in fks:
                out.append(f'<rect x="{bx + 22}" y="{ry + 3}" width="20" height="11" rx="2" class="fk"/><text x="{bx + 32}" y="{ry + 12}" class="badge">FK</text>')
            cls = "cname nn" if c["notnull"] else "cname"
            out.append(f'<text x="{x + 52}" y="{ry + 12.5}" class="{cls}">{esc(c["name"])}</text>'
                       f'<text x="{x + W - 8}" y="{ry + 12.5}" class="ctype" text-anchor="end">{esc(short_type(c["type"]))}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def erd_html(schema: dict) -> str:
    tables = {t["table"]: t for t in schema}
    order = [n for g in notes.GROUPS for col in notes.LAYOUT for n in col if notes.TABLES[n][0] == g]
    ncols = sum(len(t["columns"]) for t in schema)
    body = [f"""<section class="sheet-a3">
<header class="doc-head"><div><h1>Pickage ERD</h1>
<p class="sub">PostgreSQL 16 · Flyway V1~V13 적용 스키마 · 테이블 {len(schema)}개 · 컬럼 {ncols}개</p></div>
<p class="meta">기준 커밋 {git_rev()} · 생성 {TODAY}<br>굵은 컬럼 = NOT NULL</p></header>
{erd_svg(schema)}
</section>"""]

    body.append('<section class="sheet"><h2>1. 개요</h2>'
                "<p>Pickage 서비스 DB 는 세 영역으로 나뉜다. <b>패키지·스냅샷</b>은 deps.dev·npm 에서 수집한 원천 "
                "사실을 스냅샷 기준일 축으로 저장하고, <b>분석 결과</b>는 Spark·Python 배치와 AI 유사도 배치가 "
                "계산해 게시한 결과를 API 가 키 조회로 읽는다. <b>ETL 적재 이력</b>은 어떤 입력을 언제 게시했는지를 "
                "기록해 게시를 원자적으로 교체하고 재현할 수 있게 한다.</p>"
                "<p>스키마는 백엔드의 Flyway 마이그레이션(<code>backend/src/main/resources/db/migration</code>)이 소유하며, "
                "이 문서는 그 마이그레이션을 빈 DB 에 적용한 결과에서 자동 생성했다.</p>"
                '<table class="grid"><thead><tr><th>영역</th><th>테이블</th><th>설명</th><th>컬럼</th></tr></thead><tbody>')
    for n in order:
        g = notes.TABLES[n][0]
        label, color = notes.GROUPS[g]
        body.append(f'<tr><td class="nw"><span class="dot" style="background:{color}"></span>{esc(label.split(" (")[0])}</td>'
                    f'<td><a href="#t-{n}"><code>{n}</code></a></td><td>{esc(notes.TABLES[n][1])}</td>'
                    f'<td class="num">{len(tables[n]["columns"])}</td></tr>')
    body.append("</tbody></table>")
    body.append('<h3>관계 요약</h3><table class="grid"><thead><tr><th>참조하는 테이블 (N)</th><th>컬럼</th>'
                "<th>참조되는 테이블 (1)</th><th>비고</th></tr></thead><tbody>")
    for n in order:
        for name, cols, ref_t, ref_cols, defn in fk_list(tables[n]):
            extra = []  # 비고
            if "ON DELETE CASCADE" in defn:
                extra.append("삭제 연쇄")
            if "DEFERRABLE" in defn:
                extra.append("지연 검사")
            if ref_t == n:
                extra.append("자기 참조")
            body.append(f"<tr><td><code>{n}</code></td><td><code>{esc(', '.join(cols))}</code></td>"
                        f"<td><code>{ref_t}</code> (<code>{esc(', '.join(ref_cols))}</code>)</td><td>{' · '.join(extra)}</td></tr>")
    body.append("</tbody></table></section>")

    body.append('<section class="sheet"><h2>2. 테이블 정의서</h2>')
    for i, n in enumerate(order, 1):
        t = tables[n]
        g = notes.TABLES[n][0]
        label, color = notes.GROUPS[g]
        pks = set(pk_cols(t))
        fkmap = {}
        for _, cols, ref_t, ref_cols, _ in fk_list(t):
            for c, r in zip(cols, ref_cols):
                fkmap.setdefault(c, []).append(f"{ref_t}.{r}")
        desc = t["comment"] or notes.TABLES[n][1]
        body.append(f'<div class="tdef" id="t-{n}"><h3><span class="tag" style="background:{color}">{esc(label.split(" (")[0])}</span>'
                    f"2.{i} <code>{n}</code></h3><p>{esc(desc)}</p>")
        if t["partkey"]:
            body.append(f"<p class=\"note\">파티션 테이블 — <code>PARTITION BY {esc(t['partkey'])}</code>. "
                        "스냅샷 기준일 범위마다 파티션을 적재 시점에 만든다.</p>")
        body.append('<table class="grid cols"><thead><tr><th>#</th><th>컬럼</th><th>타입</th><th>NULL</th>'
                    "<th>기본값</th><th>키</th><th>설명</th></tr></thead><tbody>")
        for j, c in enumerate(t["columns"], 1):
            keys = []
            if c["name"] in pks:
                keys.append('<span class="k pk">PK</span>')
            if c["name"] in fkmap:
                keys.append('<span class="k fk">FK</span>')
            ref = f'<div class="ref">→ {esc(", ".join(fkmap[c["name"]]))}</div>' if c["name"] in fkmap else ""
            default = c["default"] or ""
            if len(default) > 40:
                default = default[:38] + "…"
            body.append(f'<tr><td class="num">{j}</td><td><code>{esc(c["name"])}</code></td><td><code>{esc(short_type(c["type"]))}</code></td>'
                        f'<td class="c">{"N" if c["notnull"] else "Y"}</td><td>{f"<code>{esc(default)}</code>" if default else ""}</td>'
                        f'<td class="c">{"".join(keys)}</td><td>{bold(col_desc(n, c))}{ref}</td></tr>')
        body.append("</tbody></table>")
        uniq = [c for c in t["constraints"] or [] if c["type"] in ("u", "c")]
        backing = {c["name"] for c in t["constraints"] or []}
        if uniq or t["indexes"]:
            body.append('<ul class="cons">')
            for c in uniq:
                kind = "UNIQUE" if c["type"] == "u" else "CHECK"
                d = re.sub(r"^(UNIQUE|CHECK) ", "", c["def"])
                body.append(f"<li><b>{kind}</b> <code>{esc(d)}</code></li>")
            for ix in t["indexes"] or []:
                if ix["name"] in backing:
                    continue
                d = re.sub(r"^CREATE (UNIQUE )?INDEX (\S+) ON (ONLY )?public\.\w+ USING ", r"\1\2 ", ix["def"])
                body.append(f"<li><b>INDEX</b> <code>{esc(d)}</code></li>")
            body.append("</ul>")
        body.append("</div>")
    body.append("</section>")
    return page("Pickage ERD", "\n".join(body))


# ══ API ═══════════════════════════════════════════════════════════════

ERROR_TABLE = [
    ("V001", 400, "필수 파라미터가 누락되었습니다.", "필수 파라미터(names·q·name·refs 등) 누락 또는 빈 값"),
    ("V002", 400, "요청 가능한 범위를 넘었습니다.", "개수·범위 상한 초과 (names 3개, limit 50, 동시 실행 수 등)"),
    ("V003", 400, "날짜 형식이 올바르지 않습니다. (YYYY-MM-DD)", "날짜 형식 오류 또는 존재하지 않는 날짜"),
    ("V004", 400, "값 형식이 올바르지 않습니다.", "값 형식 오류 — 패키지명 규칙·허용되지 않은 enum 값 등"),
    ("S001", 500, "일시적인 오류입니다. 잠시 후 다시 시도해 주세요.", "서버 내부 오류 (원인은 서버 로그에만 기록)"),
    ("C005", 405, "허용되지 않은 http method 접근", "HTTP 메서드 불일치 (명세 밖, 프로토콜 수준)"),
    ("C006", 404, "요청한 리소스를 찾을 수 없음", "없는 경로 또는 만료·미존재 작업 ID"),
    ("C007", 415, "지원하지 않는 Content-Type", "요청 본문 형식 불일치"),
    ("C008", 406, "요청한 Accept에 맞는 응답 형식을 제공할 수 없음", "Accept 헤더 불일치"),
]

JAVA_SCALAR = {
    "String": "string", "int": "integer", "Integer": "integer", "long": "integer", "Long": "integer",
    "short": "integer", "Short": "integer", "double": "number", "Double": "number", "float": "number",
    "BigDecimal": "number", "boolean": "boolean", "Boolean": "boolean", "LocalDate": "string(date)",
    "Instant": "string(date-time)", "OffsetDateTime": "string(date-time)", "LocalDateTime": "string(date-time)",
    "UUID": "string(uuid)", "Object": "object", "JsonNode": "object",
}


def snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def unwrap(t: str, outer: str) -> str:
    """`ResponseEntity<ApiResponseBody<X<Y>>>` 에서 outer<...> 의 안쪽을 괄호 짝으로 꺼낸다."""
    i = t.index(outer + "<") + len(outer) + 1
    depth = 1
    for j in range(i, len(t)):
        depth += {"<": 1, ">": -1}.get(t[j], 0)
        if depth == 0:
            return t[i:j]
    raise ValueError(t)


def generic_args(t: str) -> tuple[str, list[str]]:
    m = re.match(r"([\w.]+)\s*<(.*)>$", t.strip())
    if not m:
        return t.strip(), []
    from javasrc import split_top
    return m.group(1), [a.strip() for a in split_top(m.group(2))]


class Fields:
    def __init__(self, ix: JavaIndex):
        self.ix = ix

    def type_label(self, t: str, ctx) -> str:
        base, args = generic_args(t)
        if base in ("List", "Set", "Collection"):
            return f"array<{self.type_label(args[0], ctx)}>"
        if base == "Map":
            return f"map<{self.type_label(args[0], ctx)}, {self.type_label(args[1], ctx)}>"
        if base == "byte[]":
            return "binary"
        if base in JAVA_SCALAR:
            return JAVA_SCALAR[base]
        r = self.ix.resolve(base, ctx)
        if isinstance(r, EnumType):
            return "string(enum)"
        if isinstance(r, RecordType):
            return "object"
        return base

    def rows(self, t: str, ctx, prefix: str = "", depth: int = 0, seen=()):
        """record 를 (경로, 타입, 설명, 깊이) 행으로 편다."""
        base, args = generic_args(t)
        if base in ("List", "Set", "Collection"):
            yield from self.rows(args[0], ctx, prefix + "[]", depth, seen)
            return
        if base == "Map" and len(args) == 2:
            yield from self.rows(args[1], ctx, prefix + "{key}", depth, seen)
            return
        r = self.ix.resolve(base, ctx)
        if not isinstance(r, RecordType) or r.qualified in seen or depth > 6:
            return
        for c in r.components:
            name = c.json_name or snake(c.name)
            path = f"{prefix}.{name}" if prefix else name
            label = self.type_label(c.type, r.file)
            desc = c.doc
            inner = self._enum_values(c.type, r.file)
            if inner:
                desc = (desc + " " if desc else "") + "값: " + " · ".join(f"`{v}`" for v in inner)
            if c.raw_json:
                label = "object(JSON 원문)"
            nested = self._record_of(c.type, r.file)
            desc = (notes.FIELDS.get(f"{r.name}.{name}") or (short(desc) if desc else "")
                    or notes.FIELDS.get(name) or (short(nested.doc) if nested and nested.doc else ""))
            yield path, label, desc, depth
            if not c.raw_json:
                yield from self.rows(c.type, r.file, path, depth + 1, seen + (r.qualified,))

    def _record_of(self, t: str, ctx):
        base, args = generic_args(t)
        if base in ("List", "Set") and args:
            base = generic_args(args[0])[0]
        r = self.ix.resolve(base, ctx)
        return r if isinstance(r, RecordType) else None

    def _enum_values(self, t: str, ctx):
        base, args = generic_args(t)
        if base in ("List", "Set") and args:
            base = generic_args(args[0])[0]
        r = self.ix.resolve(base, ctx)
        return r.constants if isinstance(r, EnumType) else None


def field_table(rows, prefix: str = "") -> str:
    out = ['<table class="grid fields"><thead><tr><th>필드</th><th>타입</th><th>설명</th></tr></thead><tbody>']
    for path, label, desc, depth in rows:
        full = f"{prefix}{path}"
        leaf = full.rsplit(".", 1)
        shown = (f'<span class="parent">{esc(leaf[0])}.</span>{esc(leaf[1])}' if len(leaf) == 2 else esc(full))
        out.append(f'<tr><td class="fpath" style="padding-left:{8 + depth * 12}px"><code>{shown}</code></td>'
                   f'<td><code>{esc(label)}</code></td><td>{md_inline(desc)}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


def api_html(openapi: dict, rag: dict, ix: JavaIndex) -> str:
    fields = Fields(ix)
    by_key = {(e.method, e.path): e for e in ix.endpoints}
    eps = []  # (tag, method, path, opid, summary, desc, params, java Endpoint)
    for path, ops in openapi["paths"].items():
        for method, op in ops.items():
            e = by_key[(method.upper(), path)]
            params = [(p["name"], p["in"], e and next((t for n, _, t, _ in e.params if n == p["name"]), ""),
                       p.get("required", False)) for p in op.get("parameters", [])]
            eps.append((op["tags"][0], method.upper(), path, op["operationId"], op.get("summary", ""),
                        op.get("description", ""), params, e))
    for method, path, opid, params in notes.OPS["paths"]:
        e = by_key[(method, path)]
        eps.append((notes.OPS["tag"], method, path, opid, e.summary, e.description,
                    [(n, i, t, r) for n, i, t, r in params], e))
    order = {t: i for i, t in enumerate(notes.TAG_ORDER)}
    unknown = {x[2] for x in eps} - set(notes.PATH_ORDER)
    if unknown:
        raise SystemExit(f"notes.PATH_ORDER 에 없는 경로: {sorted(unknown)}")
    eps.sort(key=lambda x: (order[x[0]], notes.PATH_ORDER.index(x[2])))

    rev = git_rev()
    body = [f"""<section class="sheet cover">
<div class="cover-inner"><p class="kicker">SSAFY 15기 A506 · Pickage</p><h1>API 명세서</h1>
<p class="lead">npm 패키지 비교 의사결정 보조 서비스 Pickage 의 백엔드 REST API 와 내부 RAG 서비스 API</p>
<table class="kv"><tr><th>대상</th><td>Spring Boot API (<code>backend/</code>) · RAG API (<code>ai/rag/</code>)</td></tr>
<tr><th>엔드포인트</th><td>공개 {sum(1 for x in eps if x[0] != 'ops-weekly')}개 · 운영자 전용 {len(notes.OPS['paths'])}개 · 내부 1개</td></tr>
<tr><th>기준</th><td>커밋 <code>{rev}</code> (develop) · 생성 {TODAY}</td></tr>
<tr><th>원본</th><td>springdoc OpenAPI(<code>/v3/api-docs</code>), FastAPI <code>openapi()</code>, DTO record 소스에서 자동 생성</td></tr></table>
</div></section>"""]

    # 1. 공통 규칙
    body.append("""<section class="sheet"><h2>1. 공통 규칙</h2>
<table class="kv"><tr><th>Base URL</th><td><code>https://j15a506.p.ssafy.io/api</code> (로컬 <code>http://localhost:8080/api</code>)</td></tr>
<tr><th>인증</th><td>없음 — 공개 조회 서비스. 운영자 API(<code>/api/v1/ops/**</code>)는 nginx 에서 외부 접근을 차단한다</td></tr>
<tr><th>형식</th><td>요청·응답 JSON (UTF-8). <b>JSON 필드 이름은 snake_case</b> (Jackson 전역 설정)</td></tr>
<tr><th>배열 파라미터</th><td><code>?names=a&amp;names=b</code> 와 <code>?names=a,b</code> 를 같게 받는다. 스코프 패키지는 경로가 아니라 쿼리로 보낸다(<code>?names=@types/node</code>)</td></tr>
<tr><th>날짜</th><td><code>YYYY-MM-DD</code> (ISO-8601). 시각은 ISO-8601 UTC</td></tr>
<tr><th>문서 UI</th><td>Swagger UI <code>/swagger-ui/index.html</code> · OpenAPI <code>/v3/api-docs</code></td></tr></table>
<h3>공통 응답 형식</h3>
<div class="two"><div><p class="cap">성공</p><pre>{
  "success": true,
  "data": { … 엔드포인트별 응답 … }
}</pre></div><div><p class="cap">실패</p><pre>{
  "success": false,
  "code": "V001",
  "message": "필수 파라미터가 누락되었습니다."
}</pre></div></div>
<p>이 문서의 <b>응답 필드</b> 표는 <code>data</code> 안쪽을 기준으로 적는다. 파일을 내려주는 엔드포인트는 래퍼 없이 파일 본문을 그대로 보낸다.
자료가 없음·계산 대상 밖 같은 상태는 오류가 아니라 200 에 <code>data_status</code> 값으로 구분한다.</p>
<h3>오류 코드</h3><table class="grid"><thead><tr><th>코드</th><th>HTTP</th><th>message</th><th>발생 조건</th></tr></thead><tbody>""")
    for code, status, msg, cond in ERROR_TABLE:
        body.append(f"<tr><td><code>{code}</code></td><td class=\"c\">{status}</td><td>{esc(msg)}</td><td>{esc(cond)}</td></tr>")
    body.append("</tbody></table><p class=\"note\">V 로 시작하는 코드는 요청 자체가 규칙을 어긴 것이라 다시 보내도 결과가 같다 — 프런트는 V 코드를 재시도하지 않는다.</p></section>")

    # 2. 목록
    body.append('<section class="sheet"><h2>2. 엔드포인트 목록</h2><table class="grid list"><thead><tr>'
                "<th>#</th><th>분류</th><th>Method</th><th>URI</th><th>기능</th></tr></thead><tbody>")
    n = 0
    for tag, method, path, opid, summary, *_ in eps:
        n += 1
        body.append(f'<tr><td class="num">{n}</td><td class="c">{esc(notes.TAG_SHORT[tag])}</td><td><span class="m m-{method.lower()}">{method}</span></td>'
                    f'<td><a href="#{opid}-{method}"><code>{esc(path)}</code></a></td><td>{esc(summary)}</td></tr>')
    n += 1
    body.append(f'<tr><td class="num">{n}</td><td class="c">{esc(notes.TAG_SHORT["rag"])}</td><td><span class="m m-post">POST</span></td>'
                f'<td><a href="#rag-compare"><code>rag-api:8000/compare</code></a></td><td>README 근거 기반 공통점·차이 생성</td></tr>')
    body.append("</tbody></table></section>")

    # 3. 상세
    sec = 2
    cur_tag = None
    num = 0
    for tag, method, path, opid, summary, desc, params, e in eps:
        if tag != cur_tag:
            if cur_tag is not None:
                body.append("</section>")
            sec += 1
            sub = 0
            cur_tag = tag
            body.append(f'<section class="sheet"><h2>{sec}. {esc(notes.TAGS[tag])}</h2>')
            if tag == "ops-weekly":
                body.append('<p class="note">운영자 전용. nginx 가 <code>/api/v1/ops/</code> 를 외부에 막고 운영자는 SSH 터널로 접근한다. '
                            "Swagger 문서에서도 숨겨져 있어(<code>@Hidden</code>) 이 명세는 컨트롤러 소스에서 만들었다.</p>")
        sub += 1
        num += 1
        body.append(f'<article class="ep" id="{opid}-{method}"><h3>{sec}.{sub} {esc(summary)}</h3>'
                    f'<div class="line"><span class="m m-{method.lower()}">{method}</span><code class="uri">{esc(path)}</code></div>')
        if desc:
            body.append(f"<p>{md_inline(desc)}</p>")
        # 요청
        body.append("<h4>Request</h4>")
        if params:
            body.append('<table class="grid"><thead><tr><th>이름</th><th>위치</th><th>타입</th><th>필수</th><th>설명</th></tr></thead><tbody>')
            for name, where, jtype, _ in params:
                req = name in notes.REQUIRED
                if opid == "getSimilar" and name == "name":
                    req = True
                label = fields.type_label(jtype, None) if jtype else ""
                enum_vals = fields._enum_values(jtype, None) if jtype else None
                d = notes.PARAMS.get(name, "")
                if enum_vals and not d:
                    d = "값: " + " · ".join(f"`{v}`" for v in enum_vals)
                body.append(f'<tr><td><code>{esc(name)}</code></td><td>{where}</td><td><code>{esc(label)}</code></td>'
                            f'<td class="c">{"Y" if req else "N"}</td><td>{md_inline(d)}</td></tr>')
            body.append("</tbody></table>")
        if e.body_type:
            body.append(f'<p class="cap">Body <code>application/json</code> — <code>{esc(e.body_type)}</code></p>')
            body.append(field_table(list(fields.rows(e.body_type, None))))
        if not params and not e.body_type:
            body.append('<p class="muted">파라미터 없음</p>')
        # 응답
        body.append("<h4>Response</h4>")
        rt = e.return_type
        if "byte[]" in rt:
            ctype = "application/pdf" if "pdf" in path else "text/markdown; charset=UTF-8"
            body.append(f'<p><code>200</code> <code>{ctype}</code> — 파일 본문. <code>Content-Disposition: attachment; filename*=UTF-8\'\'…</code></p>')
        elif "ResponseEntity<String>" in rt:
            body.append('<p><code>200</code> <code>text/html; charset=UTF-8</code> — 보고서 미리보기 HTML 문서</p>')
        else:
            inner = unwrap(rt, "ApiResponseBody")
            codes = "<code>200</code>"
            if opid == "refresh":
                codes = "<code>202</code> 새 작업 수락 · <code>200</code> 신선한 결과 있음·기존 작업 참여·용량 초과"
            body.append(f'<p>{codes} <code>application/json</code> — <code>data</code>: <code>{esc(inner)}</code></p>')
            is_list = inner.startswith("List<")
            rows = list(fields.rows(generic_args(inner)[1][0] if is_list else inner, None))
            if rows:
                body.append(field_table(rows, "data[]." if is_list else "data."))
            if opid in ("startComparison", "getComparison"):
                body.append('<p class="note"><code>data.result</code> 는 RAG API <code>/compare</code> 응답 원문을 그대로 싣는다(키는 camelCase). '
                            '구조는 <a href="#rag-compare">RAG 비교 응답</a>을 따른다.</p>')
        errs = notes.ERRORS.get(opid, [])
        body.append('<p class="errs"><b>오류</b> ' + " · ".join(f"<code>{esc(x.split()[0])}</code>{esc(x[len(x.split()[0]):])}" for x in errs + ["S001"]) + "</p>")
        body.append("</article>")
    body.append("</section>")

    # RAG
    sec += 1
    req = rag["components"]["schemas"]["PackageRefIn"]["properties"]
    body.append(f"""<section class="sheet"><h2>{sec}. {esc(notes.TAGS['rag'])}</h2>
<p class="note">외부에 노출하지 않는 내부 API. 같은 compose 네트워크의 백엔드만 <code>http://rag-api:8000</code> 으로 호출한다.
백엔드 기능 비교(<code>POST /api/packages/feature-comparison</code>)가 이 API 를 비동기로 부르고 결과를 <code>result</code> 에 싣는다.</p>
<article class="ep" id="rag-compare"><h3>{sec}.1 README 근거 기반 비교 생성</h3>
<div class="line"><span class="m m-post">POST</span><code class="uri">/compare</code></div>
<p>패키지·버전별 README 인계 파일에서 근거를 추려 LLM 한 번 호출로 공통점과 패키지별 차이를 만들고, 생성물을 근거와 대조해 검증한다.</p>
<h4>Request</h4><p class="cap">Body <code>application/json</code> (FastAPI 스키마 <code>CompareRequest</code>)</p>
<table class="grid fields"><thead><tr><th>필드</th><th>타입</th><th>설명</th></tr></thead><tbody>
<tr><td><code>packages</code></td><td><code>array&lt;object&gt;</code></td><td>비교 대상 (필수)</td></tr>
<tr><td style="padding-left:20px"><code><span class="parent">packages[].</span>package</code></td><td><code>{req['package']['type']}</code></td><td>패키지명 (필수)</td></tr>
<tr><td style="padding-left:20px"><code><span class="parent">packages[].</span>version</code></td><td><code>{req['version']['type']}</code></td><td>정확한 버전 (필수)</td></tr>
</tbody></table>
<h4>Response</h4><p><code>200</code> <code>application/json</code> — 래퍼 없음, 키는 camelCase</p>
<table class="grid fields"><thead><tr><th>필드</th><th>타입</th><th>설명</th></tr></thead><tbody>
<tr><td><code>dataStatus</code></td><td><code>string</code></td><td>비교 가능 여부 상태</td></tr>
<tr><td><code>packages[]</code></td><td><code>array&lt;object&gt;</code></td><td>비교한 <code>package</code>·<code>version</code> (요청 순서)</td></tr>
<tr><td><code>common</code></td><td><code>string</code></td><td>공통점 서술 한 덩어리</td></tr>
<tr><td><code>differences[]</code></td><td><code>array&lt;object&gt;</code></td><td>패키지별 차이 문단</td></tr>
<tr><td style="padding-left:20px"><code><span class="parent">differences[].</span>package · version · body</code></td><td><code>string</code></td><td>대상 패키지·버전과 차이 본문</td></tr>
<tr><td style="padding-left:20px"><code><span class="parent">differences[].</span>marks[]</code></td><td><code>array&lt;object&gt;</code></td><td>강조 구간 — 핵심 문장 1개·핵심어 최대 3개. <code>start</code>·<code>end</code>(UTF-16, [start,end)), <code>kind</code></td></tr>
<tr><td><code>sources[]</code></td><td><code>array&lt;object&gt;</code></td><td>패키지별 README 인계 파일 상태 — <code>package</code>·<code>version</code>·<code>status</code>·<code>readmeBytes</code>·<code>proseChars</code> (못 읽은 값은 null)</td></tr>
</tbody></table>
<table class="grid"><thead><tr><th>HTTP</th><th>본문</th><th>조건</th></tr></thead><tbody>
<tr><td class="c">404</td><td><code>{{"detail": {{"code": "DOC_NOT_FOUND", "package", "version"}}}}</code></td><td>그 버전의 README 인계 파일이 아직 없음</td></tr>
<tr><td class="c">502</td><td><code>{{"detail": {{"violations": [...]}}}}</code></td><td>생성물이 근거와 어긋나 검증에서 막음</td></tr>
<tr><td class="c">422</td><td><code>{{"detail": [ValidationError]}}</code></td><td>요청 본문 형식 오류 (FastAPI 기본)</td></tr>
</tbody></table></article></section>""")
    return page("Pickage API 명세서", "\n".join(body))


# ══ PDF ═══════════════════════════════════════════════════════════════

def find_chrome() -> str | None:
    cands = [os.environ.get("CHROME"),
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")]
    return next((c for c in cands if c and Path(c).exists()), None)


def to_pdf(chrome: str, src: Path, dst: Path):
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
                    f"--print-to-pdf={dst}", src.as_uri()], check=True, capture_output=True)
    print(f"  {dst.relative_to(REPO)}  ({dst.stat().st_size // 1024} KB)")


def main():
    BUILD.mkdir(exist_ok=True)
    data = HERE / "data"
    schema = json.loads((data / "schema.json").read_text(encoding="utf-8"))
    openapi = json.loads((data / "backend-openapi.json").read_text(encoding="utf-8"))
    rag = json.loads((data / "rag-openapi.json").read_text(encoding="utf-8"))
    ix = JavaIndex(REPO / "backend" / "src" / "main" / "java")

    docs = {
        "Pickage_ERD": erd_html(schema),
        "Pickage_API_명세서": api_html(openapi, rag, ix),
        "Pickage_시스템_아키텍처": (HERE / "architecture.html").read_text(encoding="utf-8")
        .replace("/*STYLE*/", read_css()).replace("{{REV}}", git_rev()).replace("{{DATE}}", TODAY),
    }
    for name, text in docs.items():
        (BUILD / f"{name}.html").write_text(text, encoding="utf-8")
    print(f"HTML → {BUILD.relative_to(REPO)}")
    if "--html" in sys.argv:
        return
    chrome = find_chrome()
    if not chrome:
        raise SystemExit("Chrome 을 찾지 못했다. CHROME 환경변수에 실행 파일 경로를 넣을 것")
    print("PDF")
    for name in docs:
        to_pdf(chrome, BUILD / f"{name}.html", OUT / f"{name}.pdf")


if __name__ == "__main__":
    main()
