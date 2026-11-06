#!/bin/bash
# usage: refcheck.sh <list file "ref sha"> <repo> ; compares with the remote of <repo>
L="$1"; R=$(git -C "$2" ls-remote origin 'refs/heads/*'); bad=0; n=0
while read r s; do [ -z "$r" ] && continue; n=$((n+1)); got=$(echo "$R" | awk -v ref="refs/heads/$r" '$2==ref{print $1}'); case "$got" in $s*) ;; *) echo "MISMATCH $r want $s got $got"; bad=$((bad+1));; esac; done < "$L"
echo "checked=$n mismatches=$bad"
