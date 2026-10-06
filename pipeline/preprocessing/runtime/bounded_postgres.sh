#!/usr/bin/env bash
set -Eeuo pipefail

# Experimental PostgreSQL runtime. It owns only the mounted named volume and
# never touches the application's PostgreSQL container or persistent volume.
IMAGE=/var/lib/pickage-postgres-bounded/wal-staging.ext4
VOLUME=/var/lib/pickage-postgres-bounded
MOUNT=/run/pickage-postgres-bounded
MARKER=/var/lib/pickage-postgres-bounded/OWNER_UUID
LOCK=/var/lib/pickage-postgres-bounded/.lock
OWNER_ID=2d3f4f5e-95d0-4ebd-9c5b-3b8a4e3d4f12
source "$(dirname "${BASH_SOURCE[0]}")/resource_budget.sh"
REQUESTED_BYTES=${BOUNDED_POSTGRES_BYTES:-}
if [ "${BOUNDED_TEST_MODE:-0}" = 1 ]; then REQUESTED_BYTES=${BOUNDED_TEST_SIZE_BYTES:-67108864}; fi
SIZE_BYTES=$(bounded_budget_bytes postgres "$REQUESTED_BYTES")
READY_FILE=/run/pickage-postgres-ready

die(){ echo "bounded-postgres: $*" >&2; exit 2; }
need(){ command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }
for t in mount umount losetup mknod truncate mkfs.ext4 stat find setpriv flock findmnt mountpoint fstrim; do need "$t"; done
[ "$(id -u)" -eq 0 ] || die "supervisor must start as root"
rm -f -- "$READY_FILE"
[ ! -L "$VOLUME" ] && [ ! -L "$MOUNT" ] || die "runtime path is a symlink"
mkdir -p "$VOLUME" "$MOUNT"
[ ! -L "$LOCK" ] || die "lock path is a symlink"
exec 9>"$LOCK"; flock -n 9 || die "bounded PostgreSQL volume is busy"
if [ -e "$MARKER" ]; then
  [ ! -L "$MARKER" ] && [ -f "$MARKER" ] || die "invalid ownership marker"
  [ "$(cat "$MARKER")" = "$OWNER_ID" ] || die "ownership marker mismatch"
else
  find "$VOLUME" -mindepth 1 -maxdepth 1 -not -name .lock -print -quit | grep -q . && die "unmarked nonempty volume"
  printf '%s\n' "$OWNER_ID" > "$MARKER"; chmod 600 "$MARKER"
fi
[ ! -L "$IMAGE" ] || die "bounded image is a symlink"
if [ ! -e "$IMAGE" ]; then truncate -s "$SIZE_BYTES" "$IMAGE"; mkfs.ext4 -F -q "$IMAGE"; else
  [ ! -L "$IMAGE" ] && [ -f "$IMAGE" ] || die "invalid WAL/staging image"
  [ "$(stat -c '%s' "$IMAGE")" -eq "$SIZE_BYTES" ] || die "image size differs; refusing format"
fi
mounted=0; loopdev=''; child=''; clean=0
cleanup(){ set +e; rm -f -- "$READY_FILE"; if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null; wait "$child" 2>/dev/null; fi
  if [ "$mounted" -eq 1 ]; then fstrim -v "$MOUNT" >/dev/null 2>&1 || true; umount "$MOUNT" || return; fi
}
trap cleanup EXIT; trap 'exit 143' INT TERM
if mountpoint -q "$MOUNT" || findmnt -rn -M "$MOUNT" >/dev/null 2>&1; then die "mount path occupied"; fi
# AUTOCLEAR also releases the association when Docker kills the namespace.
for attempt in 1 2 3 4 5; do
  candidate=$(losetup --find)
  [[ "$candidate" =~ ^/dev/loop([0-9]+)$ ]] || die "unexpected loop device path"
  minor=${BASH_REMATCH[1]}
  [ -b "$candidate" ] || mknod "$candidate" b 7 "$minor"
  if mount -t ext4 -o loop,discard "$IMAGE" "$MOUNT"; then mounted=1; break; fi
done
[ "$mounted" -eq 1 ] || die "could not mount bounded image"
loopdev=$(findmnt -rn -M "$MOUNT" -o SOURCE)
[ "$(losetup -l -n -O AUTOCLEAR "$loopdev" | tr -d ' ')" = 1 ] || die "loop must release on namespace teardown"
[ "$(findmnt -rn -M "$MOUNT" -o FSTYPE)" = ext4 ] || die "WAL/staging filesystem is not ext4"
mkdir -p "$MOUNT/wal" "$MOUNT/staging"; chown -R 999:999 "$MOUNT"
export POSTGRES_INITDB_WALDIR="$MOUNT/wal"
export PGDATA=/var/lib/postgresql/data
if [ -s "$PGDATA/PG_VERSION" ]; then
  if [ -L "$PGDATA/pg_wal" ]; then
    [ "$(readlink -f "$PGDATA/pg_wal")" = "$MOUNT/wal" ] || die "existing PGDATA WAL points outside the bounded filesystem"
  elif [ "${POSTGRES_IMPORT_MODE:-}" = offline ]; then
    PGDATA="$PGDATA" TARGET_WAL_DIR="$MOUNT/wal" /usr/local/bin/postgres_import_wal
  else
    die "existing PGDATA has an unbounded WAL directory; migrate offline first"
  fi
fi
[ -s "$PGDATA/PG_VERSION" ] && { [ -L "$PGDATA/pg_wal" ] || die "bounded WAL symlink was not published"; [ "$(readlink -f "$PGDATA/pg_wal")" = "$MOUNT/wal" ] || die "existing PGDATA WAL points outside the bounded filesystem"; }
/usr/local/bin/docker-entrypoint.sh postgres "$@" & child=$!
# Ignore the socket-only initdb server; inspect the actual TCP-ready server.
# Changing PGDATA's recorded collation version would hide incompatible indexes.
pg_user=${POSTGRES_USER:-postgres}
pg_database=${POSTGRES_DB:-$pg_user}
ready=0
for attempt in {1..300}; do
  kill -0 "$child" 2>/dev/null || die "PostgreSQL exited before compatibility check"
  if pg_isready -h 127.0.0.1 -U "$pg_user" -d "$pg_database" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ "$ready" -eq 1 ] || die "PostgreSQL compatibility check readiness timeout"
mismatches=$(PGPASSWORD="${POSTGRES_PASSWORD:-}" psql -X -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_database" -At -c \
  "SELECT count(*) FROM pg_database WHERE datallowconn AND datcollversion IS NOT NULL AND datcollversion IS DISTINCT FROM pg_database_collation_actual_version(oid)")
[ "$mismatches" = 0 ] || die "database collation differs from runtime; preserve data and use the original compatible base image"
printf 'verified\n' > "$READY_FILE"
echo 'BOUNDED_POSTGRES_READY collation=verified'
wait "$child"; clean=1
