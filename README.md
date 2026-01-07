# OpenCCB AI 🤖

**OpenCCB AI** es una API de asistente inteligente privada, local y escalable diseñada para entornos corporativos. Utiliza **Ollama** para ejecutar modelos de lenguaje (LLM) como Llama 3, **FastAPI** para la gestión de peticiones, **Redis** para memoria conversacional de alta velocidad y **PostgreSQL** para la gestión de usuarios y seguridad.

## 🚀 Características Principales

*   **Privacidad Total:** El modelo de IA se ejecuta localmente (On-Premise); ningún dato sale de tu servidor.
*   **Streaming de Texto:** Respuestas generadas palabra por palabra en tiempo real (como ChatGPT).
*   **Memoria Contextual:** La IA recuerda lo que se habló anteriormente en la sesión gracias a Redis.
*   **Multi-Usuario:** Sistema de autenticación y gestión de sesiones con PostgreSQL.
*   **Soporte GPU:** Detección y configuración automática de tarjetas NVIDIA para máxima velocidad.
*   **Despliegue Automatizado:** Scripts incluidos para instalación en servidores Ubuntu y actualizaciones remotas.

---

## 📋 Requisitos del Sistema

Para un entorno de producción con ~60 usuarios concurrentes:

| Componente | Mínimo (Funcional) | Recomendado (Producción) |
| :--- | :--- | :--- |
| **Sistema Operativo** | Ubuntu 22.04 LTS | Ubuntu 22.04 / 24.04 LTS |
| **CPU** | 4 vCPUs | 8 vCPUs (AVX2 support) |
| **RAM** | 8 GB | **16 GB** |
| **GPU** | N/A (Modo CPU lento) | **NVIDIA (8GB+ VRAM)** |
| **Almacenamiento** | 20 GB SSD | 50 GB NVMe |

---

## 🛠️ Instalación y Configuración

### 1. Instalación en Servidor (Producción)

El proyecto incluye un script maestro (`setup.sh`) que automatiza la instalación de Docker, Drivers de NVIDIA, Nginx y la configuración de seguridad.

```bash
# 1. Clonar el repositorio
git clone https://github.com/Nurfog/openccb-ai.git
cd openccb-ai

# 2. Ejecutar el instalador
chmod +x setup.sh
./setup.sh
```

*El script generará automáticamente un archivo `.env` con contraseñas seguras y levantará los servicios en el puerto 80 (vía Nginx).*

### 2. Desarrollo Local

Si quieres ejecutarlo en tu máquina para programar:

1.  Copia el archivo de ejemplo:
    ```bash
    cp .env.example .env
    ```
2.  Levanta los servicios con Docker Compose:
    ```bash
    docker compose up --build
    ```
3.  La API estará disponible en `http://localhost:8000`.

---

## 🚢 Guías de Despliegue (Deploy)

Este proyecto soporta dos métodos de despliegue remoto sin necesidad de instalar Git en el servidor de destino.

### Opción A: Despliegue vía SSH (Push) - **Recomendado**
Sincroniza tu código local con el servidor remoto y ejecuta la instalación automáticamente.

1.  Configura tus credenciales:
    ```bash
    cp ssh_deploy.example ssh_deploy.env
    # Edita ssh_deploy.env con la IP y Usuario de tu servidor
    ```
2.  Ejecuta el despliegue:
    ```bash
    chmod +x ssh_deploy.sh
    ./ssh_deploy.sh
    ```

### Opción B: Despliegue vía FTP (Pull)
Útil si tienes el código empaquetado en un servidor FTP intermedio.

1.  Configura el acceso FTP:
    ```bash
    cp deploy.example deploy.env
    # Edita deploy.env
    ```
2.  Ejecuta el script en el servidor destino:
    ```bash
    chmod +x deploy.sh
    ./deploy.sh
    ```

---

## 🔌 Documentación de la API

### 1. Registro de Usuario
**POST** `/register`
```bash
curl -X POST "http://localhost:8000/register" \
     -H "Content-Type: application/json" \
     -d '{"username": "juan", "password": "password123"}'
```

### 2. Iniciar Sesión (Login)
**POST** `/login`
```bash
curl -X POST "http://localhost:8000/login" \
     -H "Content-Type: application/json" \
     -d '{"username": "juan", "password": "password123"}'
```

### 3. Chat con la IA (Streaming)
**POST** `/chat`

*   **Nueva Sesión:** Omite `session_id`. La API creará uno nuevo y generará un título automático.
*   **Continuar Sesión:** Envía el `session_id` devuelto anteriormente.

```bash
curl -X POST "http://localhost:8000/chat" \
     -H "Content-Type: application/json" \
     -d '{
           "username": "juan",
           "prompt": "Explícame qué es Docker en una frase",
           "session_id": "OPCIONAL_UUID_AQUI"
         }'
```
*Respuesta:* Stream de texto plano. Al final incluye un JSON con el ID de sesión: `{"session_id": "..."}`.

### 4. Listar Sesiones
**GET** `/sessions/{username}`
```bash
curl "http://localhost:8000/sessions/juan"
```
*Respuesta:*
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "description": "Explicación de Docker resumen"
  }
]
```

---

## 📂 Estructura del Proyecto

```text
openccb-ai/
├── api/                 # Código fuente del Backend (FastAPI)
│   ├── main.py          # Lógica principal y endpoints
│   ├── Dockerfile       # Definición del contenedor de la API
│   └── requirements.txt # Dependencias de Python
├── docker-compose.yml   # Orquestación de servicios (CPU base)
├── docker-compose.gpu.yml # Configuración adicional para NVIDIA GPU
├── setup.sh             # Script de instalación automática en servidor
├── ssh_deploy.sh        # Script de despliegue remoto (Push)
├── deploy.sh            # Script de despliegue vía FTP (Pull)
└── .env.example         # Plantilla de variables de entorno
```

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.