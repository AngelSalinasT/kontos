#!/usr/bin/env bash
# Instala Kontos como servicio systemd en Linux.
# Uso: sudo bash deploy/install.sh [usuario]
#
# Prerequisitos:
#   - Python 3.10+
#   - ffmpeg  (sudo apt install ffmpeg)
#   - git

set -e

USER_RUN="${1:-$(logname)}"
INSTALL_DIR="/opt/kontos"
SERVICE_FILE="/etc/systemd/system/kontos.service"

echo "==> Instalando Kontos en ${INSTALL_DIR} (usuario: ${USER_RUN})"

# Clonar o actualizar
if [ -d "${INSTALL_DIR}/.git" ]; then
    echo "==> Actualizando repo existente..."
    git -C "${INSTALL_DIR}" pull
else
    echo "==> Clonando repo..."
    git clone https://github.com/AngelSalinasT/kontos.git "${INSTALL_DIR}"
fi

chown -R "${USER_RUN}":"${USER_RUN}" "${INSTALL_DIR}"

# Entorno virtual
if [ ! -d "${INSTALL_DIR}/venv" ]; then
    echo "==> Creando entorno virtual..."
    sudo -u "${USER_RUN}" python3 -m venv "${INSTALL_DIR}/venv"
fi

echo "==> Instalando dependencias..."
sudo -u "${USER_RUN}" "${INSTALL_DIR}/venv/bin/pip" install -q --upgrade pip
sudo -u "${USER_RUN}" "${INSTALL_DIR}/venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

# Archivo .env
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
    echo ""
    echo "⚠️  Edita ${INSTALL_DIR}/.env con tus credenciales antes de continuar:"
    echo "    TELEGRAM_BOT_TOKEN=..."
    echo "    GEMINI_API_KEY=..."
    echo ""
    read -rp "Presiona Enter cuando hayas guardado el .env..."
fi

# Servicio systemd
echo "==> Instalando servicio systemd..."
sed "s/%i/${USER_RUN}/g" "${INSTALL_DIR}/deploy/kontos.service" > "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable kontos
systemctl restart kontos

echo ""
echo "✅ Kontos instalado y corriendo."
echo "   Logs:   journalctl -u kontos -f"
echo "   Estado: systemctl status kontos"
echo ""
echo "   Para cargar productos iniciales:"
echo "   sudo -u ${USER_RUN} ${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/seed.py <tu_telegram_user_id>"
