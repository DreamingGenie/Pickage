"""의존 조건 문자열 → 정확한 버전 해석의 '단순 규칙' (Spark 이식용 참조 구현).

검증 2026-09-07: 40개 requirements 파일 표본, 무작위 대상 2,393 패키지, 28,028 (대상, 조건) 조합 / 124,072 선언.
node-semver(npm 내장) maxSatisfying 과 대조 → 선언 가중 99.34% 일치, 불일치 0.14%(전부 'latest': node-semver 는 무효 범위,
npm 실제 동작인 '최고 정식 버전'으로 우리가 해석), 규칙 밖 0.52%(>=x.y.z 단독, next/alpha 태그, workspace:, npm:, github:, file:).
'최대' 선택은 deps.dev 의 VersionInfo.Ordinal 을 semver 순번으로 그대로 사용 — 27,763건 전부 node-semver 순서와 일치.

시점 t 를 적용할 때는 후보를 published_at <= t 로 먼저 걸러 넣으면 된다.
"""
import re

VER = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$')
RNG = re.compile(r'^\s*(\^|~|=)?\s*v?(\d+|x|X|\*)(?:\.(\d+|x|X|\*))?(?:\.(\d+|x|X|\*))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?\s*$')
_wild = lambda s: s in (None, 'x', 'X', '*')


def rule(req: str):
    """조건 문자열 → ('any',) | ('exact', (M,m,p), pre) | ('range', lower, upper, lower_pre) | None(규칙 밖)"""
    if req.strip() in ('', '*', 'latest'):
        return ('any',)
    m = RNG.match(req)
    if not m:
        return None
    op, M, mi, pa, pre = m.groups()
    if _wild(M):
        return ('any',)
    M = int(M)
    if _wild(mi):                                   # ^4 / 4 / 4.x
        return ('range', (M, 0, 0), (M + 1, 0, 0), None)
    mi = int(mi)
    if _wild(pa):                                   # ^4.1 / ~4.1 / 4.1 / 4.1.x
        up = (M + 1, 0, 0) if (op == '^' and M > 0) else (M, mi + 1, 0)
        return ('range', (M, mi, 0), up, None)
    pa = int(pa)
    if op == '^':                                   # caret: 0.x 는 minor, 0.0.x 는 patch 고정
        up = (M + 1, 0, 0) if M > 0 else ((0, mi + 1, 0) if mi > 0 else (0, 0, pa + 1))
        return ('range', (M, mi, pa), up, pre)
    if op == '~':
        return ('range', (M, mi, pa), (M, mi + 1, 0), pre)
    return ('exact', (M, mi, pa), pre)


def parse_versions(rows):
    """[(version_str, ordinal), ...] → [(ordinal, (M,m,p), pre, version_str)]"""
    out = []
    for v, o in rows:
        m = VER.match(v)
        if m:
            out.append((o, (int(m[1]), int(m[2]), int(m[3])), m[4], v))
    return out


def resolve(r, rows):
    """rows = parse_versions(...) (시점 t 적용 시 published_at <= t 로 미리 필터). 반환: 버전 문자열 또는 None"""
    if r[0] == 'exact':
        c = [x for x in rows if x[1] == r[1] and x[2] == r[2]]
    elif r[0] == 'any':
        c = [x for x in rows if x[2] is None]
    else:
        lo, up, lopre = r[1], r[2], r[3]
        c = [x for x in rows if lo <= x[1] < up and (x[2] is None or (lopre is not None and x[1] == lo))]
        if lopre is not None:
            lo_o = next((x[0] for x in rows if x[1] == lo and x[2] == lopre), None)
            if lo_o is not None:
                c = [x for x in c if x[1] != lo or x[0] >= lo_o]
    return max(c)[3] if c else None
