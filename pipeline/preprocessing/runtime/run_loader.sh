#!/usr/bin/env bash
set -Eeuo pipefail

workspace=${BOUNDED_WORKSPACE:?bounded workspace is required}
jar=${LOADER_JAR:-/opt/loader/curated-loader.jar}
props=${LOADER_PROPERTIES:?LOADER_PROPERTIES must point to a read-only properties file}
[ -f "$jar" ] || { echo 'loader jar is missing' >&2; exit 2; }
[ -f "$props" ] || { echo 'loader properties are missing' >&2; exit 2; }
[ ! -L "$jar" ] && [ ! -L "$props" ] || { echo 'loader inputs may not be symlinks' >&2; exit 2; }
mkdir -p "$workspace/java-tmp" "$workspace/loader-work"
log="$workspace/loader-work/loader.log"
set +e
java -Xmx512m -Djava.io.tmpdir="$workspace/java-tmp" \
  -Dpickage.curated.work-budget-bytes=3400000000 \
  -Duser.dir="$workspace/loader-work" \
  -jar "$jar" --spring.config.additional-location="file:$props" \
  --pickage.curated-load.work-dir="$workspace/loader-work" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
set -e
if [ -f "$workspace/loader-work/last-run.json" ]; then
  printf 'DB_RESULT '
  cat "$workspace/loader-work/last-run.json"
  printf '\n'
else
  printf 'DB_RESULT {"status":"UNVERIFIED","exit_code":%s}\n' "$status"
  [ "$status" -ne 0 ] || status=2
fi
exit "$status"
