#!/usr/bin/env bash
# Create or update a repository's labels from .github/labels.yml.
#
#   scripts/labels.sh Altio-AI/open-altio
#
# Needs the GitHub CLI (gh), signed in with rights to manage labels on that repository.
# --force updates a label that already exists, so running it twice is safe.
set -euo pipefail

repo="${1:?usage: scripts/labels.sh OWNER/REPO}"
file="$(cd "$(dirname "$0")/.." && pwd)/.github/labels.yml"

unquote() { local v="${1#\"}"; printf '%s' "${v%\"}"; }

name="" color="" description=""
create() {
  [ -n "$name" ] || return 0
  gh label create "$name" --repo "$repo" --color "$color" --description "$description" --force
}

while IFS= read -r line; do
  case "$line" in
    "- name: "*) create; name="$(unquote "${line#- name: }")"; color=""; description="" ;;
    "  color: "*) color="$(unquote "${line#  color: }")" ;;
    "  description: "*) description="$(unquote "${line#  description: }")" ;;
  esac
done < "$file"
create
