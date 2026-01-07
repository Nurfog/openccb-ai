#!/bin/bash
set -e

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Despliegue Remoto vía SSH (Push) ===${NC}"

# 1. Cargar configuración
if [ ! -f ssh_deploy.env ]; then
    echo -e "${RED}Error: No se encontró 'ssh_deploy.env'.${NC}"
    echo "Copia 'ssh_deploy.example' a 'ssh_deploy.env' y configura tus datos."
    exit 1
fi
source ssh_deploy.env

# Configurar comando SSH
SSH_OPTS="-p $REMOTE_PORT -o StrictHostKeyChecking=no"
if [ -n "$SSH_KEY_PATH" ]; then
    SSH_OPTS="$SSH_OPTS -i $SSH_KEY_PATH"
fi
SSH_CMD="ssh $SSH_OPTS $REMOTE_USER@$REMOTE_HOST"

echo -e "${GREEN}>>> Conectando a $REMOTE_HOST...${NC}"

# 2. Validación Remota del Servidor
echo -e "${GREEN}>>> Validando servidor remoto...${NC}"

# Verificar OS (Ubuntu)
REMOTE_OS=$($SSH_CMD "grep '^ID=' /etc/os-release | cut -d= -f2 | tr -d '\"'")
if [ "$REMOTE_OS" != "ubuntu" ]; then
    echo -e "${RED}Error: El servidor remoto no es Ubuntu (Detectado: $REMOTE_OS).${NC}"
    exit 1
fi

# Verificar RAM
REMOTE_MEM_KB=$($SSH_CMD "grep MemTotal /proc/meminfo | awk '{print \$2}'")
REMOTE_MEM_GB=$((REMOTE_MEM_KB / 1024 / 1024))

if [ "$REMOTE_MEM_GB" -lt 8 ]; then
    echo -e "${RED}Error: Memoria remota insuficiente ($REMOTE_MEM_GB GB). Mínimo 8 GB.${NC}"
    exit 1
elif [ "$REMOTE_MEM_GB" -lt 16 ]; then
    echo -e "${YELLOW}Advertencia: El servidor tiene $REMOTE_MEM_GB GB RAM. Recomendado 16 GB.${NC}"
else
    echo "Memoria Remota: $REMOTE_MEM_GB GB (OK)"
fi

# Verificar Espacio en Disco (en el home del usuario)
REMOTE_FREE_KB=$($SSH_CMD "df -k . | awk 'NR==2 {print \$4}'")
REMOTE_FREE_GB=$((REMOTE_FREE_KB / 1024 / 1024))

if [ "$REMOTE_FREE_GB" -lt 20 ]; then
    echo -e "${RED}Error: Espacio en disco remoto insuficiente ($REMOTE_FREE_GB GB). Mínimo 20 GB.${NC}"
    exit 1
else
    echo "Espacio en Disco Remoto: $REMOTE_FREE_GB GB (OK)"
fi

# 3. Sincronización de Archivos (Rsync)
echo -e "${GREEN}>>> Sincronizando archivos (compilando cambios)...${NC}"

# Crear directorio remoto si no existe
$SSH_CMD "mkdir -p $REMOTE_DIR"

# Sincronizar (Excluyendo archivos locales innecesarios)
rsync -avz --progress --delete \
    --exclude='.git' \
    --exclude='.env' \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='ssh_deploy.env' \
    --exclude='deploy.env' \
    --exclude='deploy.sh' \
    --exclude='ssh_deploy.sh' \
    -e "ssh $SSH_OPTS" \
    . $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR

# 4. Ejecución del Setup Remoto
echo -e "${GREEN}>>> Ejecutando instalación en el servidor remoto...${NC}"

# Usamos -t para forzar pseudo-terminal (útil si sudo pide password)
$SSH_CMD -t "cd $REMOTE_DIR && chmod +x setup.sh && ./setup.sh"

echo -e "${GREEN}==============================================${NC}"
echo -e "${GREEN}   DESPLIEGUE REMOTO COMPLETADO   ${NC}"
echo -e "${GREEN}==============================================${NC}"