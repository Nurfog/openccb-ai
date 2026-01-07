#!/bin/bash
set -e

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== Script de Despliegue OpenCCB AI (FTP) ===${NC}"

# 1. Cargar configuración
if [ ! -f deploy.env ]; then
    echo -e "${RED}Error: No se encontró el archivo 'deploy.env'.${NC}"
    echo "Por favor, copia 'deploy.example' a 'deploy.env' y configura tus credenciales."
    exit 1
fi
source deploy.env

# 2. Verificaciones del Sistema Operativo
echo -e "${GREEN}>>> Verificando sistema operativo...${NC}"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        echo -e "${RED}Error: Este script requiere Ubuntu. Detectado: $ID${NC}"
        exit 1
    fi
    echo "Sistema detectado: Ubuntu $VERSION_ID"
else
    echo -e "${RED}Error: No se pudo detectar el sistema operativo.${NC}"
    exit 1
fi

# 3. Verificaciones de Hardware (Requisitos del Proyecto)
echo -e "${GREEN}>>> Verificando requisitos de hardware...${NC}"

# Memoria RAM (Mínimo 8GB, Recomendado 16GB para LLMs)
MEM_TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
MEM_TOTAL_GB=$((MEM_TOTAL_KB / 1024 / 1024))

if [ "$MEM_TOTAL_GB" -lt 8 ]; then
    echo -e "${RED}Error: Memoria insuficiente ($MEM_TOTAL_GB GB). Se requieren mínimo 8 GB.${NC}"
    exit 1
elif [ "$MEM_TOTAL_GB" -lt 16 ]; then
    echo -e "${YELLOW}Advertencia: Tienes $MEM_TOTAL_GB GB de RAM. Se recomiendan 16 GB para un rendimiento óptimo.${NC}"
else
    echo "Memoria RAM: $MEM_TOTAL_GB GB (OK)"
fi

# Espacio en Disco (Mínimo 20GB libres)
FREE_SPACE_KB=$(df -k . | awk 'NR==2 {print $4}')
FREE_SPACE_GB=$((FREE_SPACE_KB / 1024 / 1024))

if [ "$FREE_SPACE_GB" -lt 20 ]; then
    echo -e "${RED}Error: Espacio en disco insuficiente ($FREE_SPACE_GB GB). Se requieren mínimo 20 GB.${NC}"
    exit 1
else
    echo "Espacio en disco: $FREE_SPACE_GB GB (OK)"
fi

# 4. Descarga del Proyecto desde FTP
echo -e "${GREEN}>>> Descargando proyecto desde FTP...${NC}"

# Instalar dependencias necesarias para el deploy
sudo apt-get update -qq
sudo apt-get install -y curl unzip

mkdir -p "$DEPLOY_DIR"
ZIP_NAME=$(basename "$FTP_FILE_PATH")

echo "Conectando a $FTP_HOST..."
curl -f -u "$FTP_USER:$FTP_PASS" "ftp://$FTP_HOST/$FTP_FILE_PATH" -o "$ZIP_NAME"

echo -e "${GREEN}>>> Descomprimindo archivos...${NC}"
unzip -o "$ZIP_NAME" -d "$DEPLOY_DIR"

# 5. Ejecutar Setup
cd "$DEPLOY_DIR"
if [ -f setup.sh ]; then
    chmod +x setup.sh
    echo -e "${GREEN}>>> Ejecutando instalador (setup.sh)...${NC}"
    ./setup.sh
else
    echo -e "${RED}Error: No se encontró 'setup.sh' en el paquete descargado.${NC}"
    exit 1
fi