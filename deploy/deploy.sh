#!/usr/bin/env bash
# deploy.sh — atualiza a aplicação em produção
# Uso: bash deploy.sh
# Executar como: sudo -u barberhub bash deploy.sh
#
# Usa "restart", não "reload": com preload_app=True (gunicorn.conf.py) um
# reload (SIGHUP) recicla os workers a partir da copia do codigo ja
# carregada em memoria no master, sem reimportar nada do disco -- nunca
# pega codigo novo. Confirmado na pratica em 2026-08-20 (ver DEPLOY.md,
# secao 6). Custa um breve downtime em vez de zero-downtime, mas e o
# unico jeito confiavel de garantir que o deploy realmente foi aplicado.

set -euo pipefail

APP_DIR="/var/www/barberhub"
VENV="$APP_DIR/venv/bin"
SERVICE="barberhub"

echo "==> [1/5] Entrando no diretório da aplicação..."
cd "$APP_DIR"

echo "==> [2/5] Atualizando código do repositório..."
git pull --ff-only

echo "==> [3/5] Instalando/atualizando dependências..."
"$VENV/pip" install -r requirements.txt --quiet --no-cache-dir

echo "==> [4/5] Aplicando migrações de banco (Alembic, idempotente)..."
FLASK_CONFIG=production "$VENV/flask" --app wsgi db upgrade

echo "==> [5/5] Reiniciando serviço..."
sudo systemctl restart "$SERVICE"

echo ""
echo "Deploy concluído com sucesso em $(date '+%Y-%m-%d %H:%M:%S')."
echo "Status: sudo systemctl status $SERVICE"
