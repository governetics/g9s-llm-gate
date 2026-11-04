#!/usr/bin/env bash
# Dump the llm-gate Postgres database from its container into a compressed
# SQL file: <OUT_DIR>/llm-gate-YYYYMMDD-HHMMSS.sql.gz
#
# A database dump alone does NOT rebuild the gate: provider credentials in
# the dump are encrypted with LLM_GATE_SALT_KEY (not rotatable -- losing it
# loses every stored credential), and the gateway/UI needs
# LLM_GATE_MASTER_KEY. Keep both keys next to the backup; a successful run
# ends with a reminder about exactly that.
#
# Env:
#   DB_CONTAINER  db container name (default: deploy-db-1; on a panel node
#                 the container name differs -- override here)
#   OUT_DIR       output directory, created if missing (default: ./backups)
#
# Exit codes: 0 backup written and archive-verified; 1 failure.

set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-deploy-db-1}"
OUT_DIR="${OUT_DIR:-./backups}"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="$OUT_DIR/llm-gate-$STAMP.sql.gz"

mkdir -p "$OUT_DIR"
echo "Dumping database 'llmgate' from container '$DB_CONTAINER' to $OUT_FILE ..."

# pipefail: a failed pg_dump must fail the whole pipeline instead of
# letting gzip wrap a truncated stream into a plausible-looking archive.
# A failed run removes the incomplete file: a leftover near-empty archive
# in the backups directory is indistinguishable from a good one at a
# glance and would betray the operator exactly when the backup is needed.
# --clean --if-exists: the dump carries DROP ... IF EXISTS, so restore.sh
# can replace the contents of a LIVE database instead of failing on the
# first CREATE TABLE of a populated schema, while a bare --clean (plain
# DROP) would abort on an empty database under ON_ERROR_STOP (measured).
if ! docker exec "$DB_CONTAINER" pg_dump --clean --if-exists -U llmgate llmgate | gzip > "$OUT_FILE"; then
    rm -f "$OUT_FILE"
    echo "ERROR: pg_dump pipeline failed; removed incomplete $OUT_FILE" >&2
    exit 1
fi

# Archive integrity check (gzip verifies the stored CRC): a corrupt dump
# must surface here, at backup time, not at restore time.
if ! gzip -t "$OUT_FILE"; then
    rm -f "$OUT_FILE"
    echo "ERROR: archive integrity check failed; removed corrupt $OUT_FILE" >&2
    exit 1
fi

SIZE="$(wc -c < "$OUT_FILE" | tr -d ' ')"
if [[ "$SIZE" -lt 1000 ]]; then
    echo "WARNING: dump is only $SIZE bytes -- empty or near-empty database?" >&2
fi

echo "Backup written: $OUT_FILE ($SIZE bytes)"
echo ""
echo "REMINDER: a database backup is useless without the keys -- store together:"
echo "  LLM_GATE_SALT_KEY    encrypts provider credentials; NOT rotatable,"
echo "                      losing it loses every stored credential"
echo "  LLM_GATE_MASTER_KEY  gateway master key / initial UI login"
