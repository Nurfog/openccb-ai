#!/bin/bash
set -e

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Iniciando Setup de OpenCCB AI ===${NC}"

# 1. Verificar sistema operativo
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        echo -e "${YELLOW}Advertencia: Este script está optimizado para Ubuntu. Tu sistema es $ID.${NC}"
    fi
else
    echo -e "${RED}Error: No se pudo detectar el sistema operativo.${NC}"
    exit 1
fi

# 2. Instalar dependencias básicas y Docker
echo -e "${GREEN}>>> Actualizando sistema e instalando dependencias...${NC}"
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release git openssl nginx

# Instalar Docker si no existe
if ! command -v docker &> /dev/null; then
    echo -e "${GREEN}>>> Instalando Docker...${NC}"
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
    echo -e "${GREEN}>>> Docker ya está instalado.${NC}"
fi

# 3. Configuración de Variables de Entorno (.env)
echo -e "${GREEN}>>> Configurando entorno...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
    # Generar contraseña segura para DB
    DB_PASS=$(openssl rand -base64 12)
    sed -i "s/POSTGRES_PASSWORD=cambiar_esta_password/POSTGRES_PASSWORD=$DB_PASS/" .env
    echo -e "${GREEN}>>> Archivo .env creado con contraseñas seguras.${NC}"
else
    echo -e "${YELLOW}>>> Archivo .env ya existe, se omitirá la generación.${NC}"
fi

# 4. Detección de GPU y Configuración
echo -e "${GREEN}>>> Verificando hardware (GPU)...${NC}"
COMPOSE_FILES="docker-compose.yml"

if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}>>> GPU NVIDIA detectada!${NC}"
    
    # Instalar NVIDIA Container Toolkit si no existe
    if ! dpkg -l | grep -q nvidia-container-toolkit; then
        echo -e "${GREEN}>>> Instalando NVIDIA Container Toolkit...${NC}"
        distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
        curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
        curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        sudo apt-get update
        sudo apt-get install -y -q nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker
    fi
    
    # Activar configuración GPU en .env
    COMPOSE_FILES="docker-compose.yml:docker-compose.gpu.yml"
    echo -e "${GREEN}>>> Modo GPU activado.${NC}"
else
    echo -e "${YELLOW}>>> No se detectó GPU NVIDIA. Se usará modo CPU.${NC}"
fi

# Actualizar COMPOSE_FILE en .env
sed -i "s|^COMPOSE_FILE=.*|COMPOSE_FILE=$COMPOSE_FILES|" .env

# 5. Configuración de Nginx (Reverse Proxy)
echo -e "${GREEN}>>> Configurando Nginx como Proxy Inverso...${NC}"

# Obtener IP local o dominio
SERVER_IP=$(hostname -I | awk '{print $1}')
echo -e "Configurando Nginx para escuchar en: $SERVER_IP"

NGINX_CONF="/etc/nginx/sites-available/openccb-ai"

sudo bash -c "cat > $NGINX_CONF" <<EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Activar sitio y reiniciar Nginx
if [ ! -L /etc/nginx/sites-enabled/openccb-ai ]; then
    sudo ln -s /etc/nginx/sites-available/openccb-ai /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
fi

sudo nginx -t && sudo systemctl restart nginx

# 6. Despliegue con Docker Compose
echo -e "${GREEN}>>> Construyendo y levantando contenedores...${NC}"
sudo docker compose up -d --build

echo -e "${GREEN}==============================================${NC}"
echo -e "${GREEN}   INSTALACIÓN COMPLETADA EXITOSAMENTE   ${NC}"
echo -e "${GREEN}==============================================${NC}"
echo -e "La API está disponible en: http://$SERVER_IP"
echo -e "Ollama está corriendo en segundo plano."
echo -e "Credenciales de base de datos guardadas en .env"
echo -e ""
echo -e "Para ver los logs: sudo docker compose logs -f"