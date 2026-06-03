#!/usr/bin/env bash
# Despliega Kontos a archlinux (push-based, vía SSH/Tailscale).
# Uso:  ./deploy/deploy.sh
# Requiere: entrada "Host archlinux" en ~/.ssh/config y sudo sin password
#           para systemctl restart kontos.service en el host (o se pedirá).
set -euo pipefail

HOST="${KONTOS_HOST:-archlinux}"
REMOTE_DIR="${KONTOS_REMOTE_DIR:-~/kontos}"
SERVICE="kontos.service"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Archivos/carpetas de la app a sincronizar (excluye datos y entorno).
cd "$LOCAL_DIR"

echo "▶ Desplegando Kontos a $HOST:$REMOTE_DIR"

echo "  1/5 · backup remoto"
ssh "$HOST" "cd $REMOTE_DIR && ts=\$(date +%Y%m%d_%H%M%S) && mkdir -p .deploy_bak/\$ts && \
  rsync -aR --quiet \$(git ls-files '*.py' 2>/dev/null || echo bot.py graph.py) .deploy_bak/\$ts/ 2>/dev/null; \
  echo '    backup .deploy_bak/'\$ts"

echo "  2/5 · sincronizando código (rsync)"
rsync -az --delete \
  --include='*/' \
  --include='*.py' \
  --include='requirements.txt' \
  --include='*.service' \
  --exclude='*' \
  --exclude='gastos.db' \
  --exclude='venv/' \
  --exclude='.deploy_bak/' \
  ./ "$HOST:$REMOTE_DIR/"

echo "  3/5 · validando sintaxis con el venv remoto"
ssh "$HOST" "cd $REMOTE_DIR && ./venv/bin/python -m py_compile \$(git ls-files '*.py' 2>/dev/null || find . -name '*.py' -not -path './venv/*' -not -path './.deploy_bak/*')"

echo "  4/5 · instalando dependencias (si cambió requirements.txt)"
ssh "$HOST" "cd $REMOTE_DIR && ./venv/bin/pip install -q -r requirements.txt"

echo "  5/5 · reiniciando $SERVICE"
ssh "$HOST" "sudo systemctl restart $SERVICE && sleep 5 && systemctl is-active $SERVICE"

echo "▶ Verificación post-deploy:"
ssh "$HOST" "journalctl -u $SERVICE --no-pager -n 5 --since '20 seconds ago' | grep -E 'escuchando|started|ERROR|Traceback' || journalctl -u $SERVICE --no-pager -n 3"

echo "✅ Deploy completo."
