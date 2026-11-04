#!/usr/bin/env bash
# Restore a llm-gate Postgres dump (.sql or .sql.gz, as written by
# backup.sh) into the db container.
#
# DANGEROUS: restores ON TOP OF the live database -- models, virtual keys
# and spend history are replaced by the dump content. The dump is usable
# only together with the SAME LLM_GATE_SALT_KEY that encrypted the stored
# credentials (not rotatable) -- keys and dumps live together.
#
# Usage:
#   restore.sh <IN_FILE> [--yes]
#   DB_CONTAINER=<name> restore.sh <IN_FILE> --yes
#   RESTORE_YES=1 DB_CONTAINER=<name> restore.sh <IN_FILE>
#
#   IN_FILE        dump file (.sql or .sql.gz), positional, required
#   --yes          confirmation flag (positional); the same confirmation
#                  via env RESTORE_YES=1 (an env variable cannot legally
#                  be named "--yes", hence RESTORE_YES)
#   DB_CONTAINER   db container name (default: deploy-db-1; on a panel
#                  node the container name differs -- override here)
#
# Exit codes: 0 restored; 1 restore failed; 2 bad invocation / not
# confirmed. Without confirmation the script refuses before touching the
# database.

set -euo pipefail

DB_CONTAINER="${DB_CONTAINER:-deploy-db-1}"
IN_FILE=""
CONFIRMED=0

usage() {
    cat <<'USAGE'
usage: restore.sh <IN_FILE> [--yes]
  IN_FILE        dump file (.sql or .sql.gz), positional, required
  --yes          confirmation flag; same via env RESTORE_YES=1
  DB_CONTAINER   db container name (default: deploy-db-1; env)
Restores ON TOP OF the live database; refuses without --yes / RESTORE_YES=1.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --yes) CONFIRMED=1 ;;
        -h|--help) usage; exit 0 ;;
        *)
            if [[ -n "$IN_FILE" ]]; then
                echo "ERROR: unexpected extra argument '$arg'." >&2
                usage >&2
                exit 2
            fi
            IN_FILE="$arg"
            ;;
    esac
done

# Env confirmation channel (alternative to the positional --yes flag).
if [[ "${RESTORE_YES:-0}" == 1 ]]; then
    CONFIRMED=1
fi

if [[ -z "$IN_FILE" ]]; then
    echo "ERROR: IN_FILE is required (.sql or .sql.gz)." >&2
    usage >&2
    exit 2
fi
if [[ ! -f "$IN_FILE" || ! -r "$IN_FILE" ]]; then
    echo "ERROR: cannot read dump file '$IN_FILE'." >&2
    exit 2
fi

echo "About to RESTORE over the LIVE database:"
echo "  container: $DB_CONTAINER"
echo "  dump     : $IN_FILE"
echo "Everything currently in the database will be overwritten."
if [[ "$CONFIRMED" != 1 ]]; then
    echo "ERROR: not confirmed. Re-run with the --yes flag (or RESTORE_YES=1)." >&2
    exit 2
fi

# ON_ERROR_STOP: psql aborts on the first SQL error instead of pressing on
# and leaving a silently half-restored database; pipefail carries a failed
# gunzip (corrupt archive) out of the pipeline the same way.
if [[ "$IN_FILE" == *.gz ]]; then
    gzip -cd "$IN_FILE" \
        | docker exec -i "$DB_CONTAINER" psql -U llmgate -d llmgate -v ON_ERROR_STOP=1
else
    docker exec -i "$DB_CONTAINER" psql -U llmgate -d llmgate -v ON_ERROR_STOP=1 \
        < "$IN_FILE"
fi

echo "Restore complete."
echo "Reminder: credentials in the dump decrypt only under the original"
echo "LLM_GATE_SALT_KEY; the UI login needs LLM_GATE_MASTER_KEY."
