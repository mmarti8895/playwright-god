#!/usr/bin/env bash
# Block any attempt to commit a real env file.
# example.env / .env.example are allowed; everything else matching .env* is rejected.
set -euo pipefail

status=0
for f in "$@"; do
    base="$(basename "$f")"
    case "$base" in
        example.env|.env.example)
            continue
            ;;
        .env|.env.*|.envrc|.envrc.*)
            echo "ERROR: refusing to commit env file: $f"
            echo "       (these are gitignored to protect secrets; use example.env for templates)"
            status=1
            ;;
    esac
done
exit "$status"
