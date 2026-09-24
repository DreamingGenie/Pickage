#!/bin/sh
#
# refresh_inputs.sh — 산출물 생성기의 입력(src/data/*.json)을 현재 코드에서 다시 뽑는다
#
#   sh docs/제출산출물/src/refresh_inputs.sh
#   python docs/제출산출물/src/build.py
#
# 마이그레이션·컨트롤러·RAG API 가 바뀌었을 때만 돌리면 된다. DTO 설명만 바뀐 경우는
# build.py 가 자바 소스를 직접 읽으므로 이 단계가 필요 없다.
#
# ⚠ 실데이터가 든 로컬 DB(pickage-local-postgres, 15432)는 건드리지 않는다.
#   일회용 Postgres 컨테이너를 따로 띄우고, 백엔드를 그 DB 에 붙여 Flyway 가 빈 DB 에
#   V1~Vn 을 적용하게 한 뒤 스키마와 /v3/api-docs 를 읽는다. 끝나면 컨테이너를 지운다.
#
# 필요: Docker, Java 21, Python 3 (fastapi 가 설치된 환경), curl

set -eu

ROOT=$(git rev-parse --show-toplevel)
DATA="$ROOT/docs/제출산출물/src/data"
PG=pickage-docgen-pg
PG_PORT=15499
API_PORT=18099

cleanup() {
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  docker rm -f "$PG" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "1) 일회용 Postgres ($PG, 127.0.0.1:$PG_PORT)"
docker rm -f "$PG" >/dev/null 2>&1 || true
docker run -d --name "$PG" -e POSTGRES_PASSWORD=docgen -e POSTGRES_DB=docgen \
  -p "127.0.0.1:$PG_PORT:5432" postgres:16 >/dev/null
until docker exec "$PG" pg_isready -U postgres -d docgen >/dev/null 2>&1; do sleep 1; done

echo "2) 백엔드 기동 → Flyway 적용 (:$API_PORT)"
# bootRun 이 아니라 jar 를 직접 띄운다 — Gradle 데몬 밑의 자식 JVM 은 $! 로 잡히지 않아
# 끝나고도 포트를 쥔 채 남는다(Windows 에서 확인).
( cd "$ROOT/backend" && ./gradlew bootJar -q )
JAR=$(ls "$ROOT"/backend/build/libs/*.jar | grep -v -- '-plain' | head -1)
SPRING_DATASOURCE_URL="jdbc:postgresql://localhost:$PG_PORT/docgen" \
SPRING_DATASOURCE_PASSWORD=docgen SERVER_PORT="$API_PORT" \
  java -jar "$JAR" >"${TMPDIR:-/tmp}/docgen-api.log" 2>&1 &
API_PID=$!
i=0
until curl -sf "http://localhost:$API_PORT/v3/api-docs" -o "$DATA/backend-openapi.json"; do
  i=$((i + 1))
  [ "$i" -gt 180 ] && { echo "백엔드가 3분 안에 뜨지 않았다: ${TMPDIR:-/tmp}/docgen-api.log" >&2; exit 1; }
  sleep 1
done

echo "3) 스키마 추출"
docker exec -i "$PG" psql -U postgres -d docgen -At <"$ROOT/docs/제출산출물/src/schema.sql" >"$DATA/schema.json"

echo "4) RAG API OpenAPI"
( cd "$ROOT" && python -c "
import json
from ai.rag.main import create_app
json.dump(create_app(lambda p: None).openapi(), open(r'$DATA/rag-openapi.json', 'w', encoding='utf-8'))
" )

echo "5) JSON 정렬 (diff 가 읽히게)"
python - "$DATA" <<'PY'
import json, sys, pathlib
for f in pathlib.Path(sys.argv[1]).glob("*.json"):
    d = json.loads(f.read_text(encoding="utf-8"))
    d.pop("servers", None) if isinstance(d, dict) else None
    f.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
PY
echo "완료 — 이제 python docs/제출산출물/src/build.py"
