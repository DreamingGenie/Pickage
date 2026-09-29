#!/usr/bin/env bash
set -Eeuo pipefail

# One-shot local/server-safe supervisor for the preprocessing runtime.
# The privileged section only creates/mounts the image in its dedicated volume;
# the actual pipeline is always executed as uid 1000.

IMAGE=/var/lib/pickage-bounded/scratch.ext4
MOUNT=/run/pickage-bounded
VOLUME=/var/lib/pickage-bounded
MARKER=/var/lib/pickage-bounded/OWNER_UUID
LOCK=/var/lib/pickage-bounded/.lock
OWNER_ID=8b2f0d34-7fd2-4b77-9c2a-7a2d0cf88e1e
# Installed alongside this supervisor, and also usable from the source tree.
source "$(dirname "${BASH_SOURCE[0]}")/resource_budget.sh"
WORKSPACE_ROLE=$(cat "$(dirname "${BASH_SOURCE[0]}")/workspace.role")
[[ "$WORKSPACE_ROLE" = preprocess || "$WORKSPACE_ROLE" = loader ]] || { echo 'invalid workspace role' >&2; exit 2; }
REQUESTED_BYTES=${BOUNDED_WORKSPACE_BYTES:-}
if [ "${BOUNDED_TEST_MODE:-0}" = 1 ]; then
  REQUESTED_BYTES=${BOUNDED_TEST_SIZE_BYTES:-67108864}
fi
SIZE_BYTES=$(bounded_budget_bytes "$WORKSPACE_ROLE" "$REQUESTED_BYTES")
RUN_UID=1000
RUN_GID=1000

die() { echo "bounded-workspace: $*" >&2; exit 2; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"; }

for tool in mount umount losetup mknod truncate mkfs.ext4 stat find setpriv flock findmnt mountpoint fstrim; do need "$tool"; done
[ "$(id -u)" -eq 0 ] || die "supervisor must start as root; pipeline is dropped to uid ${RUN_UID}"
[[ "$IMAGE" == "$VOLUME/"* ]] || die "image path must stay inside the dedicated volume"
[[ "$MARKER" == "$VOLUME/"* ]] || die "marker path must stay inside the dedicated volume"

[ ! -L "$VOLUME" ] || die "dedicated volume path is a symlink"
[ ! -L "$MOUNT" ] || die "mount path is a symlink"
mkdir -p "$VOLUME" "$MOUNT"
[ ! -L "$LOCK" ] || die "lock path is a symlink"
exec 9>"$LOCK"
flock -n 9 || die "dedicated volume is already in use"
if [ -e "$MARKER" ]; then
  [ ! -L "$MARKER" ] || die "ownership marker is a symlink"
  [ -f "$MARKER" ] || die "ownership marker is not a regular file"
  [ "$(cat "$MARKER")" = "$OWNER_ID" ] || die "dedicated volume ownership marker mismatch"
else
  find "$VOLUME" -mindepth 1 -maxdepth 1 -not -name .lock -print -quit | grep -q . && die "unmarked nonempty dedicated volume; refusing to format"
  printf '%s\n' "$OWNER_ID" > "$MARKER"
  chmod 600 "$MARKER"
fi

[ ! -L "$IMAGE" ] || die "bounded image is a symlink"
if [ ! -e "$IMAGE" ]; then
  truncate -s "$SIZE_BYTES" "$IMAGE"
  mkfs.ext4 -F -q "$IMAGE"
else
  [ ! -L "$IMAGE" ] || die "bounded image is a symlink"
  [ -f "$IMAGE" ] || die "bounded image is not a regular file"
  [ "$(stat -c '%s' "$IMAGE")" -eq "$SIZE_BYTES" ] || die "existing image size differs; refusing format"
fi

mounted=0
loopdev=''
child=''
image_owned=1
cleanup() {
  set +e
  if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null; wait "$child" 2>/dev/null; fi
  unmounted=1
  if [ "$mounted" -eq 1 ]; then
    fstrim -v "$MOUNT" >/dev/null 2>&1 || true
    umount "$MOUNT" || unmounted=0
  fi
  detached=1
  if losetup -j "$IMAGE" | grep -q .; then detached=0; fi
  if [ "$unmounted" -eq 1 ] && [ "$detached" -eq 1 ] && [ "$image_owned" -eq 1 ] && [ -f "$IMAGE" ] && [ ! -L "$IMAGE" ]; then
    rm -f -- "$IMAGE"
  fi
}
trap cleanup EXIT
trap 'exit 143' TERM INT

if mountpoint -q "$MOUNT" || findmnt -rn -M "$MOUNT" >/dev/null 2>&1; then
  die "mount path is already occupied; refusing to reuse an unknown mount"
fi
# Docker's private /dev may lack a newly allocated kernel loop device. Create
# only its device node, then let mount allocate an AUTOCLEAR loop. Explicitly
# detaching a device after umount could affect a subsequent owner's reuse.
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
[ "$(findmnt -rn -M "$MOUNT" -o FSTYPE)" = ext4 ] || die "mounted filesystem is not ext4"
chown "$RUN_UID:$RUN_GID" "$MOUNT"

setpriv --reuid="$RUN_UID" --regid="$RUN_GID" --clear-groups \
  --no-new-privs --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
  env BOUNDED_WORKSPACE="$MOUNT" BOUNDED_SCRATCH_LIMIT_BYTES="$SIZE_BYTES" \
  "$@" &
child=$!
wait "$child"
