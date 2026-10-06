#!/usr/bin/env bash
set -Eeuo pipefail
script="$(dirname "$0")/run_loader.sh"
bash -n "$script"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf 'fake jar\n' > "$tmp/fake.jar"
printf 'spring.main.web-application-type=none\n' > "$tmp/loader.properties"
cat > "$tmp/java" <<'EOF'
#!/usr/bin/env bash
set -eu
work=''
for arg in "$@"; do
  case "$arg" in --pickage.curated-load.work-dir=*) work=${arg#*=} ;; esac
done
[ "$work" = "$BOUNDED_WORKSPACE/loader-work" ]
if [ "${TEST_MISSING_STATE:-0}" = 0 ]; then
  printf '{"status":"PUBLISHED","rows":1}' > "$work/last-run.json"
fi
exit "${TEST_JAVA_EXIT:-0}"
EOF
chmod +x "$tmp/java"
PATH="$tmp:$PATH" JAVA_HOME= LOADER_JAR="$tmp/fake.jar" LOADER_PROPERTIES="$tmp/loader.properties" \
  BOUNDED_WORKSPACE="$tmp/work" bash "$script" > "$tmp/out"
grep -q 'DB_RESULT {"status":"PUBLISHED","rows":1}' "$tmp/out"
set +e
PATH="$tmp:$PATH" TEST_JAVA_EXIT=7 LOADER_JAR="$tmp/fake.jar" LOADER_PROPERTIES="$tmp/loader.properties" \
  BOUNDED_WORKSPACE="$tmp/failure" bash "$script" > "$tmp/failure.out"
status=$?
set -e
[ "$status" -eq 7 ]
set +e
PATH="$tmp:$PATH" TEST_MISSING_STATE=1 LOADER_JAR="$tmp/fake.jar" LOADER_PROPERTIES="$tmp/loader.properties" \
  BOUNDED_WORKSPACE="$tmp/missing" bash "$script" > "$tmp/missing.out"
status=$?
set -e
[ "$status" -eq 2 ]
grep -q 'UNVERIFIED' "$tmp/missing.out"
echo 'loader wrapper fixture passed'
