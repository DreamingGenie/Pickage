#!/usr/bin/env bash
set -Eeuo pipefail

# Explicit, offline-only migration helper. It must run against a stopped,
# separately mounted fixture. It never touches the project/server DB by itself.
die(){ echo "postgres-import-wal: $*" >&2; exit 2; }
[ "${POSTGRES_IMPORT_MODE:-}" = offline ] || die "set POSTGRES_IMPORT_MODE=offline explicitly"
[ "$(id -u)" -eq 0 ] || die "must run as root"
PGDATA=/var/lib/postgresql/data
TARGET=/run/pickage-postgres-bounded/wal
[ -d "$PGDATA" ] && [ -f "$PGDATA/PG_VERSION" ] || die "PGDATA is missing"
[ "$(cat "$PGDATA/PG_VERSION")" = 16 ] || die "only PostgreSQL 16 is supported"
command -v pg_controldata >/dev/null || die "pg_controldata is required"
state=$(pg_controldata "$PGDATA" | sed -n 's/^Database cluster state:[[:space:]]*//p')
[ "$state" = "shut down" ] || die "cluster is not cleanly shut down: $state"
[ -d "$TARGET" ] && [ ! -L "$TARGET" ] || die "target WAL directory is invalid"
[ "$(findmnt -rn -T "$TARGET" -o TARGET)" = /run/pickage-postgres-bounded ] || die "target must be on the mounted bounded filesystem"
mkdir -p "$TARGET"
src="$PGDATA/pg_wal"
[ -d "$src" ] && [ ! -L "$src" ] || die "source pg_wal must be an internal directory"
find "$src" -type l -print -quit | grep -q . && die "source WAL contains a symlink"
find "$TARGET" -mindepth 1 -print -quit | grep -q . && die "target WAL directory is not empty"
manifest=$(mktemp)
trap 'rm -f "$manifest" "$manifest.src" "$manifest.dst"' EXIT
tar -C "$src" -cf - . | tar -C "$TARGET" -xf -
(cd "$src" && find . -type f -printf '%P\0' | sort -z | xargs -0 sha256sum) > "$manifest.src"
(cd "$TARGET" && find . -type f -printf '%P\0' | sort -z | xargs -0 sha256sum) > "$manifest.dst"
cmp -s "$manifest.src" "$manifest.dst" || die "copied WAL checksum manifest differs"
backup="$PGDATA/pg_wal.import-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mv "$src" "$backup"
ln -s "$TARGET" "$src"
echo "WAL_IMPORT_COMPLETE backup=$backup target=$TARGET"
