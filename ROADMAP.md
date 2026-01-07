# 🗺️ Roadmap de OpenCCB AI

Este documento describe el plan de desarrollo, los hitos alcanzados y las futuras implementaciones para transformar **OpenCCB AI** en una solución corporativa robusta.

## ✅ Fase 1: Cimientos y Despliegue (Completado)
- [x] **Core:** API funcional con FastAPI y Streaming de texto.
- [x] **IA Local:** Integración con Ollama y modelo Llama 3.
- [x] **Infraestructura:** Dockerización completa con soporte para CPU y GPU (NVIDIA).
- [x] **Memoria:** Gestión de contexto de conversación utilizando Redis.
- [x] **Despliegue:** Scripts de automatización para instalación (`setup.sh`) y actualizaciones remotas (`ssh_deploy.sh`).
- [x] **Seguridad Básica:** Hashing de contraseñas y gestión de sesiones.

## 🚧 Fase 2: Consolidación de Datos (En Progreso)
*Objetivo: Migrar la persistencia temporal a una estructura relacional sólida para 60+ usuarios.*

- [ ] **Migración de Auth a PostgreSQL:** Mover la gestión de usuarios de Redis a PostgreSQL (actualmente en Redis por simplicidad).
- [ ] **Historial Persistente:** Guardar el log completo de los chats en base de datos para auditoría (no solo el contexto en memoria).
- [ ] **Gestión de Roles:** Crear roles (Admin, Usuario) para limitar el acceso a ciertos modelos o configuraciones.
- [ ] **Conectores de Datos:** Implementar funciones para que la IA pueda consultar bases de datos externas (SQL) y responder preguntas sobre stock o datos internos.

## 🎨 Fase 3: Experiencia de Usuario (Frontend)
*Objetivo: Facilitar el uso de la herramienta para usuarios no técnicos.*

- [ ] **Interfaz Web:** Desarrollar un frontend ligero (Streamlit o React) que consuma la API.
- [ ] **Gestión de Sesiones Visual:** Panel lateral para ver, renombrar y eliminar conversaciones antiguas.
- [ ] **Feedback:** Botones de "Me gusta" / "No me gusta" en las respuestas para evaluar la calidad del modelo.

## 🧠 Fase 4: Capacidades Avanzadas (RAG)
*Objetivo: Que la IA "lea" documentos de la empresa.*

- [ ] **Ingesta de Documentos:** Endpoint para subir PDFs, Excel o Word.
- [ ] **Base de Datos Vectorial:** Integrar `pgvector` en PostgreSQL para búsquedas semánticas.
- [ ] **Citas:** Que la IA indique en qué documento basó su respuesta.

## 🛡️ Fase 5: Enterprise & DevOps
*Objetivo: Estabilidad y monitoreo para producción.*

- [ ] **Monitoreo:** Dashboard (Grafana/Prometheus) para visualizar uso de GPU, latencia y tokens/segundo.
- [ ] **Rate Limiting:** Evitar que un solo usuario sature la GPU con demasiadas peticiones.
- [ ] **HTTPS Automático:** Integrar Certbot/Let's Encrypt en el script de despliegue.
- [ ] **CI/CD:** Pipelines de testeo automático antes del despliegue.

---

### 🤝 Contribución
Si deseas trabajar en alguna de estas tareas, por favor abre un *Issue* o crea un *Pull Request*.