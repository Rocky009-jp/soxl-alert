#!/bin/bash
# usage: refcheck.sh protected.txt lsremote.txt
fail=0
while read sha ref; do
  got=$(awk -v r="refs/heads/$ref" '$2==r{print $1}' "$2")
  if [ "$got" != "$sha" ]; then echo "MISMATCH $ref want=$sha got=$got"; fail=1; fi
done < "$1"
n=$(wc -l < "$1"); echo "checked $n refs, fail=$fail"
