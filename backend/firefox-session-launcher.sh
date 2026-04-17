#!/bin/bash
# Wrapper to launch Firefox in a unique profile per X display.
# This prevents Firefox from reusing an existing instance across separate session displays.

set -euo pipefail

FIREFOX_BIN="/usr/lib/firefox-esr/firefox-esr"
DISPLAY_VALUE="${DISPLAY:-:0}"
DISPLAY_NUM="${DISPLAY_VALUE#:}"
PROFILE_DIR="/tmp/firefox-profile-${DISPLAY_NUM}"

mkdir -p "$PROFILE_DIR"

args=()
skip_next=false
for arg in "$@"; do
  if [[ "$skip_next" == true ]]; then
    skip_next=false
    continue
  fi

  case "$arg" in
    -new-window)
      args+=("--new-instance")
      ;;
    --new-instance)
      args+=("--new-instance")
      ;;
    --no-remote)
      ;;
    -profile|--profile)
      skip_next=true
      ;;
    *)
      args+=("$arg")
      ;;
  esac
done

export MOZ_NO_REMOTE=1
exec "$FIREFOX_BIN" --new-instance --profile "$PROFILE_DIR" "${args[@]}"
