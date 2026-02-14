#!/usr/bin/env bash
set -euo pipefail

REPO=""
BRANCH=""
COMMIT=""
OUT=""
FORCE_REFRESH="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2;;
    --branch) BRANCH="$2"; shift 2;;
    --commit) COMMIT="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --force-refresh) FORCE_REFRESH="1"; shift 1;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

[[ -z "$REPO" || -z "$OUT" ]] && {
  echo "Usage: $0 --repo <url> [--branch main] [--commit sha] --out <dir>"
  exit 1
}

mkdir -p "$(dirname "$OUT")"

normalize_repo_url() {
  local u="$1"
  u="${u%"${u##*[![:space:]]}"}"
  u="${u%/}"
  echo "${u%.git}"
}

if [[ "$FORCE_REFRESH" == "1" && -d "$OUT" ]]; then
  rm -rf "$OUT"
fi

should_clone="1"
if [[ -d "$OUT/.git" ]]; then
  existing_origin="$(git -C "$OUT" config --get remote.origin.url 2>/dev/null || true)"
  if [[ -n "$existing_origin" ]]; then
    if [[ "$(normalize_repo_url "$existing_origin")" == "$(normalize_repo_url "$REPO")" ]]; then
      should_clone="0"
      echo "[repo] reusing existing clone: $OUT"
    fi
  fi
fi

if [[ "$should_clone" == "1" ]]; then
  rm -rf "$OUT"
  echo "[clone] $REPO"
  if [[ -n "$BRANCH" ]]; then
    git clone --depth 1 --branch "$BRANCH" "$REPO" "$OUT"
  else
    git clone --depth 1 "$REPO" "$OUT"
  fi
fi

cd "$OUT"

if [[ -n "$COMMIT" ]]; then
  echo "[checkout] $COMMIT"
  if ! git checkout "$COMMIT"; then
    git fetch --depth 50 origin "$COMMIT" || true
    git checkout "$COMMIT"
  fi
elif [[ -n "$BRANCH" ]]; then
  if ! git checkout "$BRANCH"; then
    git fetch --depth 50 origin "$BRANCH" || true
    git checkout "$BRANCH"
  fi
fi

echo "[done] repo at $OUT"
