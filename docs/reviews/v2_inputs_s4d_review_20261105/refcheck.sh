#!/bin/bash
# usage: refcheck.sh <protected list> ; compares each ref with the remote (full SHA)
H=$(mktemp); git ls-remote --heads https://github.com/Rocky009-jp/soxl-alert > "$H" || exit 9
ok=0; bad=0
while read ref sha; do
  got=$(awk -v r="refs/heads/$ref" '$2==r{print $1}' "$H")
  if [ "$got" = "$sha" ]; then ok=$((ok+1)); else bad=$((bad+1)); echo "MISMATCH $ref want=$sha got=$got"; fi
done < "$1"
echo "match=$ok mismatch=$bad"
