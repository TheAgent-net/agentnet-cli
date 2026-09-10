#!/usr/bin/env bash
# Install the Corgi specialist on the AgentNet EC2 box (nginx + systemd).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/TheAgent-net/agentnet-cli.git}"
BRANCH="${BRANCH:-cursor/corgi-specialized-bot-ea09}"
INSTALL_ROOT="${INSTALL_ROOT:-$HOME/agentnet-cli}"
SERVICE_USER="${SERVICE_USER:-$(id -un)}"

if [[ ! -d "$INSTALL_ROOT/.git" ]]; then
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_ROOT"
else
  git -C "$INSTALL_ROOT" fetch origin "$BRANCH"
  git -C "$INSTALL_ROOT" checkout "$BRANCH"
  git -C "$INSTALL_ROOT" pull --ff-only origin "$BRANCH"
fi

cd "$INSTALL_ROOT"
if command -v uv >/dev/null 2>&1; then
  uv sync
  BIN="$INSTALL_ROOT/.venv/bin/agentnet"
else
  python3 -m venv .venv
  .venv/bin/pip install -e .
  BIN="$INSTALL_ROOT/.venv/bin/agentnet"
fi

UNIT=/etc/systemd/system/corgi-specialist.service
sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=AgentNet Corgi specialist (homepage + POST /chat)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_ROOT}
ExecStart=${BIN} corgi-serve --host 127.0.0.1 --port 8765
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now corgi-specialist.service

NGINX_SRC="$INSTALL_ROOT/src/agentnet_cli/partners/corgi/deploy/nginx-corgi.agentnet.it.com.conf"
if [[ -d /etc/nginx/sites-enabled ]]; then
  sudo cp "$NGINX_SRC" /etc/nginx/sites-available/corgi.agentnet.it.com
  sudo ln -sfn /etc/nginx/sites-available/corgi.agentnet.it.com /etc/nginx/sites-enabled/corgi.agentnet.it.com
elif [[ -d /etc/nginx/conf.d ]]; then
  sudo cp "$NGINX_SRC" /etc/nginx/conf.d/corgi.agentnet.it.com.conf
fi
if command -v nginx >/dev/null 2>&1; then
  sudo nginx -t
  sudo systemctl reload nginx
fi

echo "Corgi specialist is up on 127.0.0.1:8765"
curl -sS http://127.0.0.1:8765/health
echo
