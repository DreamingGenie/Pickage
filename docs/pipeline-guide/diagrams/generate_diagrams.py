"""Generate the self-contained SVG diagrams used by the pipeline guide.

The generator intentionally uses only the Python standard library so the SVGs
can be rebuilt in a clean checkout without a diagram package or network access.
"""
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
INK, TEAL, PALE, ORANGE, MUTED = "#1d2c2a", "#143b36", "#f2f7f4", "#d97736", "#5a706b"
ACTIVE_MARKER = "diagram"


def esc(value):
    return escape(str(value))


def text(x, y, value, size=20, fill=INK, weight="400", anchor="start"):
    return f'<text x="{x}" y="{y}" font-family="Arial, Pretendard, sans-serif" font-size="{size}px" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(value)}</text>'


def rect(x, y, w, h, label, detail=None, fill="white", stroke=TEAL, title=None):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="2"/>']
    out.append(text(x + 18, y + 32, label, 21, INK, "700"))
    if detail:
        for i, line in enumerate(detail):
            out.append(text(x + 18, y + 61 + i * 25, line, 18, MUTED))
    if title:
        out.append(f'<title>{esc(title)}</title>')
    return "".join(out)


def arrow(x1, y1, x2, y2, label=None, color=ORANGE, dashed=False):
    marker = f"{ACTIVE_MARKER}-arrow-dashed" if dashed else f"{ACTIVE_MARKER}-arrow"
    line = f'<path d="M {x1} {y1} L {x2} {y2}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" marker-end="url(#{marker})"' + (' stroke-dasharray="8 8"' if dashed else '') + '/>'
    if label:
        line += text((x1 + x2) / 2, (y1 + y2) / 2 - 9, label, 18, color, "700", "middle")
    return line


def svg(name, title, description, width, height, content):
    uid = f"{name}-title"
    did = f"{name}-desc"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{uid} {did}">
  <title id="{uid}">{esc(title)}</title>
  <desc id="{did}">{esc(description)}</desc>
  <defs>
    <marker id="{name}-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{ORANGE}"/></marker>
    <marker id="{name}-arrow-dashed" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{MUTED}"/></marker>
  </defs>
  <rect width="100%" height="100%" fill="{PALE}"/>
  {content}
</svg>
'''


def overview(mobile=False):
    global ACTIVE_MARKER
    ACTIVE_MARKER = "overview-mobile" if mobile else "overview-desktop"
    if not mobile:
        c = [text(40, 48, "raw → curated → PostgreSQL", 28, TEAL, "700"), text(40, 79, "한 스냅샷을 검증하고, 계산 결과를 게시한 뒤 적재합니다.", 18, MUTED)]
        cards = [(40, 145, "1  수집 완료", ["MinIO raw", "manifest + _SUCCESS"], "#ffffff"),
                 (350, 145, "2  전처리", ["6개 단계 실행", "검증 후 bundle 게시"], "#fff8f3"),
                 (660, 145, "3  DB 적재", ["Spring Boot 배치", "PostgreSQL 트랜잭션 반영"], "#ffffff")]
        for x, y, l, d, f in cards: c.append(rect(x, y, 240, 150, l, d, f))
        c += [arrow(280, 220, 340, 220), arrow(590, 220, 650, 220),
              rect(40, 370, 860, 145, "공통 안전장치", ["입력·코드 계약  |  단계별 checkpoint  |  실패 로그·재시도  |  완료 bundle만 소비"], "#e7f0ec", TEAL),
              text(40, 570, "읽는 법", 19, TEAL, "700"), text(40, 602, "주황색 화살표는 데이터/제어 흐름, 점선은 직접 실행이 아닌 개념적 연결입니다.", 18, MUTED)]
        return svg("overview-desktop", "전체 파이프라인 개요", "raw 수집 완료에서 Curated 게시와 PostgreSQL 적재까지의 세 단계 흐름", 940, 650, "".join(c))
    c = [text(20, 40, "raw → curated → DB", 25, TEAL, "700"), text(20, 70, "스냅샷 하나의 처리 흐름", 18, MUTED)]
    cards = [(20, 105, "1  수집 완료", ["MinIO raw", "manifest + _SUCCESS"]), (20, 270, "2  전처리", ["6개 단계", "검증 후 bundle 게시"]), (20, 435, "3  DB 적재", ["Spring Boot", "PostgreSQL 트랜잭션"])]
    for x, y, l, d in cards: c.append(rect(x, y, 300, 125, l, d, "#ffffff" if y != 270 else "#fff8f3"))
    c += [arrow(170, 230, 170, 262, ""), arrow(170, 395, 170, 427, ""), rect(20, 600, 300, 125, "항상 함께 검증", ["계약·SHA·checkpoint", "로그·재시도·완료 marker"], "#e7f0ec"), text(20, 790, "주황색 선 = 흐름", 18, MUTED)]
    return svg("overview-mobile", "전체 파이프라인 개요 모바일", "스냅샷 처리의 세 단계와 공통 검증 장치", 340, 840, "".join(c))


def stages(mobile=False):
    global ACTIVE_MARKER
    ACTIVE_MARKER = "stages-mobile" if mobile else "stages-desktop"
    labels = [("snapshot", "기준일·달력", "Projects로 기준일 생성"), ("package_version", "패키지·버전", "versions와 요구사항"), ("downloads", "다운로드", "스냅샷 구간 집계"), ("repository", "저장소 지표", "연결·품질 기록"), ("package_snapshot", "패키지 스냅샷", "다운로드·저장소 지표"), ("dependents", "역의존", "요구사항·버전·기준일")]
    if not mobile:
        c = [text(40, 48, "전처리 6단계", 28, TEAL, "700"), text(40, 79, "실제 실행 순서입니다. 각 단계는 승인된 산출물을 다음 단계에 넘깁니다.", 18, MUTED)]
        positions = [(40, 140), (330, 140), (620, 140), (620, 355), (330, 355), (40, 355)]
        for i, (key, l, d) in enumerate(labels):
            x, y = positions[i]
            detail = {"snapshot": "기준일·달력", "package_version": "versions_min/full", "downloads": "구간 다운로드", "repository": "저장소 지표", "package_snapshot": "다운로드·저장소 지표", "dependents": "요구사항·버전·기준일"}[key]
            c.append(rect(x, y, 250, 112, f"{i+1}  {l}", [detail, f"stage: {key}"], "#fff8f3" if key == "repository" else "#ffffff"))
        for a, b in zip(positions, positions[1:]):
            ax, ay = a; bx, by = b
            if by == ay and bx > ax: c.append(arrow(ax + 250, ay + 56, bx - 10, by + 56))
            elif by == ay: c.append(arrow(ax, ay + 56, bx + 260, by + 56))
            else: c.append(arrow(ax + 125, ay + 112, bx + 125, by - 10))
        c.append(text(40, 555, "manifest와 _SUCCESS가 확인된 산출물만 다음 단계의 입력이 됩니다.", 18, MUTED))
        return svg("stages-desktop", "전처리 단계 흐름", "6개 전처리 단계를 실제 실행 순서대로 보여주는 흐름", 940, 620, "".join(c))
    c = [text(20, 40, "전처리 6단계", 25, TEAL, "700"), text(20, 70, "실행 순서대로 읽습니다.", 18, MUTED)]
    for i, (key, l, d) in enumerate(labels):
        y = 100 + i * 112
        c.append(rect(20, y, 300, 82, f"{i+1}  {l}", [d], "#fff8f3" if key == "repository" else "#ffffff"))
        if i < len(labels) - 1: c.append(arrow(170, y + 82, 170, y + 104))
    c.append(text(20, 805, "단계마다 manifest와 marker 기록", 18, MUTED))
    return svg("stages-mobile", "전처리 단계 흐름 모바일", "6개 전처리 단계를 세로로 읽는 도식", 340, 850, "".join(c))


def records(mobile=False):
    global ACTIVE_MARKER
    ACTIVE_MARKER = "records-mobile" if mobile else "records-desktop"
    if not mobile:
        c = [text(40, 48, "raw 행이 curated 행이 되는 방식", 28, TEAL, "700"), text(40, 79, "설명용 작은 예시입니다. 실제 행 수와 값은 스냅샷마다 다릅니다.", 18, MUTED)]
        c += [rect(40, 135, 210, 155, "raw 입력", ["versions_min", "requirements", "projects", "downloads"], "#ffffff"), arrow(260, 212, 315, 212), rect(325, 135, 230, 155, "curated 산출물", ["package_version", "package_snapshot", "dependents"], "#fff8f3"), arrow(565, 212, 620, 212), rect(630, 135, 150, 155, "MinIO", ["bundle", "_SUCCESS"], "#ffffff"), arrow(705, 290, 705, 350),
              rect(40, 360, 860, 145, "PostgreSQL 결과", ["package·version 마스터", "package_snapshot · package_version_snapshot", "dependents_count: NULL만 제외, 0은 저장"], "#e7f0ec"), text(40, 560, "package는 이름·ID, version은 패키지 버전, snapshot은 관측 기준일로 식별합니다.", 18, MUTED)]
        return svg("records-desktop", "데이터 레코드 흐름", "raw 테이블이 curated 산출물과 MinIO bundle로 변환되는 개념도", 940, 630, "".join(c))
    c = [text(20, 40, "raw → curated → DB", 25, TEAL, "700"), text(20, 70, "데이터 형태의 변화", 18, MUTED), rect(20, 105, 300, 150, "raw 입력", ["versions_min", "requirements", "projects", "downloads"]), arrow(170, 275, 170, 300), rect(20, 330, 300, 125, "curated", ["package_version", "package_snapshot", "dependents"], "#fff8f3"), arrow(170, 470, 170, 495), rect(20, 525, 300, 105, "MinIO bundle", ["manifest + _SUCCESS", "SHA로 고정"], "#ffffff"), arrow(170, 645, 170, 670), rect(20, 700, 300, 105, "PostgreSQL", ["마스터·두 snapshot 테이블", "dependents NULL 제외"], "#e7f0ec")]
    return svg("records-mobile", "데이터 레코드 흐름 모바일", "raw가 Curated bundle을 거쳐 PostgreSQL의 마스터와 snapshot 테이블로 반영되는 흐름", 340, 820, "".join(c))


def loading(mobile=False):
    global ACTIVE_MARKER
    ACTIVE_MARKER = "loading-mobile" if mobile else "loading-desktop"
    if not mobile:
        c = [text(40, 48, "Curated bundle → PostgreSQL", 28, TEAL, "700"), text(40, 79, "Spring Boot 적재기는 게시된 bundle만 소비합니다.", 18, MUTED)]
        c += [rect(40, 135, 230, 145, "공통 검증", ["manifest SHA", "marker·파일 목록"], "#ffffff"), arrow(280, 207, 345, 207), rect(355, 135, 230, 145, "파일 변환", ["Parquet → TSV", "초기 적재는 64MiB"], "#fff8f3"), arrow(595, 207, 660, 207), rect(670, 135, 230, 145, "트랜잭션", ["서비스 테이블", "한 스냅샷 단위"], "#ffffff"), rect(40, 365, 410, 150, "INITIAL  빈 DB", ["64MiB 묶음 COPY", "실패하면 초기 적재부터 재실행"], "#e7f0ec"), rect(490, 365, 410, 150, "WEEKLY  기존 DB", ["파일별 staging·receipt", "검증된 staging 재사용"], "#e7f0ec"), text(40, 570, "두 경로 모두 parent bundle과 현재 DB 기준을 확인한 뒤 트랜잭션을 확정합니다.", 18, MUTED)]
        return svg("loading-desktop", "Curated bundle PostgreSQL 적재", "검증과 변환을 거쳐 Spring Boot가 PostgreSQL에 트랜잭션으로 반영하는 흐름", 940, 640, "".join(c))
    c = [text(20, 40, "bundle → PostgreSQL", 25, TEAL, "700"), text(20, 70, "Spring Boot 적재 흐름", 18, MUTED), rect(20, 105, 300, 88, "1  공통 검증", ["manifest SHA·marker"]), arrow(170, 208, 170, 233), rect(20, 258, 300, 88, "2  파일 변환", ["Parquet → TSV"], "#fff8f3"), arrow(170, 361, 90, 395), arrow(170, 361, 250, 395), rect(20, 410, 140, 110, "INITIAL", ["빈 DB", "64MiB COPY"], "#ffffff"), rect(180, 410, 140, 110, "WEEKLY", ["기존 DB", "staging"], "#e7f0ec"), arrow(90, 530, 170, 565), arrow(250, 530, 170, 565), rect(20, 580, 300, 88, "3  최종 트랜잭션", ["서비스 테이블 확정"])]
    return svg("loading-mobile", "Curated bundle PostgreSQL 적재 모바일", "초기 적재와 주간 적재 중 하나를 선택하는 Spring Boot 흐름", 340, 730, "".join(c))


def recovery(mobile=False):
    global ACTIVE_MARKER
    ACTIVE_MARKER = "recovery-mobile" if mobile else "recovery-desktop"
    if not mobile:
        c = [text(40, 48, "실패해도 이어갈 수 있는 실행", 28, TEAL, "700"), text(40, 79, "상태와 증거를 남겨 원인을 고친 뒤 같은 입력을 재개합니다.", 18, MUTED)]
        c += [rect(40, 140, 190, 125, "WAITING_INPUT", ["입력·부모 대기"]),
              arrow(240, 202, 290, 202),
              rect(300, 140, 190, 125, "RUNNING", ["단계 실행", "events 기록"], "#fff8f3"),
              arrow(500, 202, 550, 202),
              rect(560, 140, 190, 125, "COMPLETE", ["bundle 게시", "다음 회차 허용"]),
              arrow(360, 270, 360, 345), text(375, 315, "일시 실패", 18, ORANGE),
              rect(300, 355, 190, 125, "FAILED", ["재시도 대기", "10분~1시간"], "#fff8f3"),
              f'<path d="M300 417 H260 V240 H290" fill="none" stroke="{ORANGE}" stroke-width="3" marker-end="url(#{ACTIVE_MARKER}-arrow)"/>',
              text(155, 335, "재시도", 18, TEAL),
              f'<path d="M470 265 V300 H710 V345" fill="none" stroke="{ORANGE}" stroke-width="3" marker-end="url(#{ACTIVE_MARKER}-arrow)"/>',
              text(555, 288, "계약 오류", 18, ORANGE),
              arrow(500, 417, 610, 417), text(510, 450, "연속 10회", 18, ORANGE),
              rect(620, 355, 220, 125, "BLOCKED", ["자동 중단", "원인 해결 필요"], "#e7f0ec"),
              rect(40, 550, 860, 120, "재개 조건", ["같은 run_id·입력·코드 계약일 때 checkpoint를 재검증하고 재사용합니다."]),
              text(40, 715, "계약 오류는 즉시 차단합니다. 일시 실패는 정해진 횟수까지만 재시도합니다.", 18, MUTED)]
        return svg("recovery-desktop", "실패와 재개 흐름", "입력 대기, 실행, 실패 재시도, 차단, 완료 상태의 개념적 흐름", 940, 780, "".join(c))
    c = [text(20, 40, "실패와 재개", 25, TEAL, "700"), text(20, 70, "원인 해결 후 같은 실행 재개", 18, MUTED), rect(20, 105, 300, 78, "WAITING_INPUT", ["입력·부모 대기"]), arrow(170, 195, 170, 220), rect(20, 245, 300, 78, "RUNNING", ["단계 실행·events"]), arrow(170, 335, 170, 360), arrow(170, 360, 90, 380), arrow(170, 360, 250, 380), rect(20, 395, 140, 92, "COMPLETE", ["bundle 게시"]), rect(180, 395, 140, 92, "FAILED", ["재시도 대기"], "#fff8f3"), f'<path d="M320 440 H332 V285 H320" fill="none" stroke="{ORANGE}" stroke-width="2" marker-end="url(#{ACTIVE_MARKER}-arrow)"/>', arrow(250, 487, 250, 515), rect(180, 525, 140, 105, "BLOCKED", ["계약 오류", "연속10회"], "#e7f0ec"), text(20, 665, "checkpoint 재사용 조건: 동일 계약", 18, MUTED), text(20, 700, "BLOCKED는 원인 해결 후 수동 재개", 18, MUTED)]
    return svg("recovery-mobile", "실패와 재개 흐름 모바일", "실행 상태와 재개 조건을 세로로 보여주는 개념도", 340, 760, "".join(c))


def storage(mobile=False):
    global ACTIVE_MARKER
    ACTIVE_MARKER = "storage-mobile" if mobile else "storage-desktop"
    if not mobile:
        c = [text(40, 48, "무엇을 어디에 보관하는가", 28, TEAL, "700"), text(40, 79, "영구 데이터와 실행 중 임시 공간을 구분합니다.", 18, MUTED)]
        c += [rect(40, 135, 260, 155, "MinIO raw", ["수집 원본", "영구 보관 대상"], "#ffffff"), arrow(310, 212, 365, 212), rect(375, 135, 260, 155, "작업 공간", ["checkpoint·events", "임시 파일·spill"], "#fff8f3"), arrow(645, 212, 700, 212), rect(710, 135, 190, 155, "MinIO curated", ["완료 bundle", "영구 결과"], "#ffffff"), rect(40, 370, 860, 150, "처리용 공간 배정", ["전처리 28GB  +  PostgreSQL 17GB  +  로더 4GB  +  로그 0.5GB  =  49.5GB", "이 계산은 처리용 합계이며, 영구 raw와 최종 Curated·DB 데이터는 제외합니다."], "#e7f0ec"), text(40, 575, "PostgreSQL에는 서비스 테이블과 staging·receipt가 함께 사용됩니다.", 18, MUTED)]
        return svg("storage-desktop", "저장소와 작업 공간", "raw, 작업 공간, curated, PostgreSQL의 저장 역할과 흐름", 940, 640, "".join(c))
    c = [text(20, 40, "저장소 역할", 25, TEAL, "700"), text(20, 70, "영구 데이터와 작업 공간을 구분", 18, MUTED), rect(20, 105, 300, 92, "MinIO raw", ["수집 원본·manifest"]), arrow(170, 212, 170, 237), rect(20, 262, 300, 110, "작업 공간", ["checkpoint·events", "임시 파일·spill"], "#fff8f3"), arrow(170, 387, 170, 412), rect(20, 437, 300, 92, "MinIO curated", ["완료 bundle·_SUCCESS"]), arrow(170, 544, 170, 569), rect(20, 594, 300, 108, "PostgreSQL", ["서비스·staging/receipt"], "#e7f0ec"), rect(20, 730, 300, 100, "처리용 합계", ["합계 49.5GB", "영구 데이터 제외"], "#ffffff")]
    return svg("storage-mobile", "저장소와 작업 공간 모바일", "raw부터 PostgreSQL까지 저장 역할과 처리용 공간 배정을 보여주는 도식", 340, 860, "".join(c))


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    pairs = {"overview": overview, "stages": stages, "records": records, "loading": loading, "recovery": recovery, "storage": storage}
    for name, fn in pairs.items():
        (ROOT / f"{name}.svg").write_text(fn(False), encoding="utf-8")
        (ROOT / f"{name}-mobile.svg").write_text(fn(True), encoding="utf-8")


if __name__ == "__main__":
    main()

