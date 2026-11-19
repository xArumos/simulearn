#!/usr/bin/env bash
# Back up the local MongoDB (demo chats, ratings, transcripts) to one timestamped, gzipped archive.
#   bash scripts/db_backup.sh            -> ~/simulearn-backups/simulearn-YYYYMMDD-HHMMSS.archive.gz
#   SIMULEARN_BACKUP_DIR=/mnt/d/backups bash scripts/db_backup.sh
# Uses mongodump on this machine if installed, otherwise the copy inside the simulearn-mongo container
# (docker-compose.yml). Settings come from the shell or the repo's .env: MONGODB_URI, MONGODB_DATABASE,
# SIMULEARN_BACKUP_DIR. The folder must be outside the repo, because the dumps hold chat text.
#
# Restore (adds the documents back; add --drop to replace collections that already exist):
#   mongorestore --uri=mongodb://127.0.0.1:27017 --gzip --archive=FILE
#   docker exec -i simulearn-mongo mongorestore --gzip --archive < FILE
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

# .env fills in only what the shell has not set.
if [ -f "$repo/.env" ]; then
  while IFS='=' read -r key value; do
    key="${key#export }"; key="${key//[[:space:]]/}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
    if [ -z "${!key+x}" ]; then export "$key=$value"; fi
  done < <(grep -v '^[[:space:]]*#' "$repo/.env")
fi

uri="${MONGODB_URI:-mongodb://127.0.0.1:27017}"
db="${MONGODB_DATABASE:-simulearn}"
dest="${SIMULEARN_BACKUP_DIR:-$HOME/simulearn-backups}"
container="${SIMULEARN_MONGO_CONTAINER:-simulearn-mongo}"

dest_abs="$(realpath -m "$dest")"
case "$dest_abs/" in
  "$repo"/*) echo "error: backup folder $dest_abs is inside the repo; pick one outside it (SIMULEARN_BACKUP_DIR)" >&2; exit 1;;
esac

file="$dest_abs/$db-$(date +%Y%m%d-%H%M%S).archive.gz"

if command -v mongodump >/dev/null 2>&1; then
  mkdir -p "$dest_abs"
  mongodump --uri="$uri" --db="$db" --gzip --archive="$file"
elif command -v docker >/dev/null 2>&1 && [ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" = "true" ]; then
  mkdir -p "$dest_abs"
  # Inside the container Mongo listens on its own 127.0.0.1:27017.
  docker exec "$container" mongodump --db="$db" --gzip --archive > "$file"
else
  echo "error: no mongodump found. Install the MongoDB Database Tools, or start the container with 'docker compose up -d'." >&2
  exit 1
fi

if [ ! -s "$file" ]; then
  echo "error: backup $file is empty" >&2
  rm -f "$file"
  exit 1
fi
chmod 600 "$file"
echo "backup written: $file ($(du -h "$file" | cut -f1))"
