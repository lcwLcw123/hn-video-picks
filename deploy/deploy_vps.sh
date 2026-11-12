#!/usr/bin/env bash
# Upload site/ to the VPS as a new release and switch the `current` symlink atomically.
# Only touches /srv/claude-tube. Keeps the last 5 releases for instant rollback.
# Usage: deploy/deploy_vps.sh            (rollback: deploy/deploy_vps.sh --rollback)
set -euo pipefail
HOST="${DEPLOY_HOST:-root@167.172.86.125}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/hackertube_digitalocean_ed25519}"
BASE=/srv/claude-tube
SSH=(ssh -o IdentitiesOnly=yes -o BatchMode=yes -i "$KEY" "$HOST")
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--rollback" ]]; then
  "${SSH[@]}" "set -e; cd $BASE/releases; prev=\$(ls -1 | sort | tail -2 | head -1); ln -sfn $BASE/releases/\$prev $BASE/current.tmp && mv -Tf $BASE/current.tmp $BASE/current; echo rolled back to \$prev"
  exit 0
fi

REL=$(date -u +%Y%m%dT%H%M%SZ)
"${SSH[@]}" "mkdir -p $BASE/releases/$REL"
rsync -az --delete -e "ssh -o IdentitiesOnly=yes -o BatchMode=yes -i $KEY" site/ "$HOST:$BASE/releases/$REL/"
"${SSH[@]}" "set -e; chmod -R a+rX $BASE/releases/$REL; ln -sfn $BASE/releases/$REL $BASE/current.tmp && mv -Tf $BASE/current.tmp $BASE/current; cd $BASE/releases && ls -1 | sort | head -n -5 | xargs -r rm -rf; echo \"current: \$(readlink $BASE/current)\"; du -sh $BASE/current/"
