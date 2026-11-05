#!/bin/bash
# The mode line of the S4-E request (third edition, section 3 item 17), run for every combination. No network.
for ev in schedule workflow_dispatch; do for im in "" auto dry live; do for vm in dry live; do
  EVENT_NAME=$ev INPUT_MODE=$im V2_MODE=$vm bash -c 'case "$EVENT_NAME:$INPUT_MODE" in schedule:*|*:auto) MODE="$V2_MODE";; *) MODE="$INPUT_MODE";; esac; echo "$EVENT_NAME|$INPUT_MODE|$V2_MODE -> [$MODE]"'
done; done; done
