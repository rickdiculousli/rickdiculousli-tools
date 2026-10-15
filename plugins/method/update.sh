#!/usr/bin/env bash
# Refresh the method plugin's skills from their upstreams, pinned in UPSTREAM.
#
#   ./update.sh                                   re-copy every skill at its pinned commit
#   ./update.sh --to obra/superpowers=main ...    move a repo to another ref (branch, tag or commit)
#   ./update.sh --check [--to <repo>=<ref>]...    show the diff per skill and change nothing
#
# Each repo is fetched shallow into a temp dir at its pin, or at the ref --to names. Every skill
# directory listed for it is diffed against skills/<name> here; without --check it is then copied
# over and the repo's new commit is written to UPSTREAM. --check exits 1 when any skill differs.
# It also says when a repo's default branch has moved past the pin.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
upstream="$here/UPSTREAM"
check=0
overrides=()

usage() { sed -n '2,11s/^# \{0,1\}//p' "$0"; }

while [ $# -gt 0 ]; do
  case $1 in
    --check) check=1 ;;
    --to)
      [ $# -ge 2 ] || { echo "update.sh: --to needs <repo>=<ref>" >&2; exit 2; }
      case $2 in *=?*) ;; *) echo "update.sh: --to needs <repo>=<ref>, got '$2'" >&2; exit 2 ;; esac
      overrides+=("$2"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "update.sh: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# Every --to must name a repo in UPSTREAM.
for o in ${overrides[@]+"${overrides[@]}"}; do
  grep -q "^${o%%=*} " "$upstream" || { echo "update.sh: ${o%%=*} is not in UPSTREAM" >&2; exit 2; }
done

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

ref_for() {   # the --to ref for a repo, else its pin
  local repo=$1 pin=$2 o
  for o in ${overrides[@]+"${overrides[@]}"}; do
    [ "${o%%=*}" = "$repo" ] && { echo "${o#*=}"; return; }
  done
  echo "$pin"
}

changed=0
pins=()   # "repo commit" for every repo, in UPSTREAM order
while read -r repo pin paths <&3; do
  case $repo in ''|\#*) continue ;; esac
  ref=$(ref_for "$repo" "$pin")
  url="https://github.com/$repo.git"
  dir="$work/${repo//\//_}"
  git init -q "$dir"
  git -C "$dir" fetch -q --depth 1 "$url" "$ref"
  git -C "$dir" -c advice.detachedHead=false checkout -q FETCH_HEAD
  commit=$(git -C "$dir" rev-parse HEAD)
  pins+=("$repo $commit")
  echo "== $repo at $ref ($commit)"
  if [ "$ref" = "$pin" ]; then
    head=$(git ls-remote "$url" HEAD | cut -f1)
    [ -n "$head" ] && [ "$head" != "$pin" ] && echo "   upstream HEAD is $head; --to $repo=HEAD to see it"
  fi
  for path in $paths; do
    name=$(basename "$path")
    [ -d "$dir/$path" ] || { echo "update.sh: $repo has no $path at $ref" >&2; exit 1; }
    if diff -ruN "$here/skills/$name" "$dir/$path" >"$work/diff"; then
      echo "-- $name: unchanged"
    else
      echo "-- $name: differs"
      cat "$work/diff"
      changed=1
    fi
    if [ $check = 0 ]; then
      rm -rf "${here:?}/skills/$name"
      cp -R "$dir/$path" "$here/skills/$name"
    fi
  done
done 3<"$upstream"

if [ $check = 1 ]; then
  exit $changed
fi

# Record the commits copied: rewrite each repo line's commit, keep everything else.
for p in "${pins[@]}"; do
  awk -v repo="${p%% *}" -v commit="${p#* }" '$1 == repo { $2 = commit } { print }' "$upstream" >"$work/UPSTREAM"
  cat "$work/UPSTREAM" >"$upstream"
done
if [ $changed = 1 ]; then
  echo "Skills changed: bump the version in plugin.json and run python3 scripts/sync_marketplaces.py."
fi
