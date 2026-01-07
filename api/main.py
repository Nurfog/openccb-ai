# main.py
# Este será el punto de entrada para nuestra API.

import os
import json
import requests
import redis
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from passlib.context import CryptContext
from typing import List, Optional

app = FastAPI()

# Conexión a Redis para guardar el historial de conversaciones
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, db=0)

# Configuración para hashing de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    username: str
    prompt: str
    model: str = "llama3"  # Asegúrate de tener este modelo descargado en Ollama
    session_id: Optional[str] = None # Identificador opcional

@app.get("/")
def read_root():
    return {"message": "Hola, soy tu asistente de IA personal."}

@app.post("/register")
def register(user: User):
    if redis_client.exists(f"user:{user.username}:auth"):
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    hashed_password = pwd_context.hash(user.password)
    redis_client.set(f"user:{user.username}:auth", hashed_password)
    return {"message": "Usuario registrado exitosamente"}

@app.post("/login")
def login(user: User):
    stored_hash = redis_client.get(f"user:{user.username}:auth")
    if not stored_hash or not pwd_context.verify(user.password, stored_hash.decode('utf-8')):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    return {"message": "Login exitoso", "username": user.username}

@app.get("/sessions/{username}")
def get_sessions(username: str):
    # Obtener todos los IDs de sesión del usuario
    session_ids = redis_client.smembers(f"user:{username}:sessions")
    sessions = []
    for sid in session_ids:
        sid = sid.decode('utf-8')
        desc = redis_client.get(f"session:{sid}:description")
        sessions.append({
            "id": sid,
            "description": desc.decode('utf-8') if desc else "Nueva conversación"
        })
    return sessions

@app.post("/chat")
def chat(request: ChatRequest):
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    # Validar que el usuario exista (simple check)
    if not redis_client.exists(f"user:{request.username}:auth"):
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    # Generar session_id si no viene uno
    session_id = request.session_id if request.session_id else str(uuid.uuid4())
    
    # Verificar si es una sesión nueva para este usuario
    is_new_session = not redis_client.sismember(f"user:{request.username}:sessions", session_id)
    
    if is_new_session:
        # Registrar la sesión al usuario
        redis_client.sadd(f"user:{request.username}:sessions", session_id)
        
        # Generar título con IA (síncrono por simplicidad)
        try:
            title_prompt = f"Genera un título muy corto (máximo 5 palabras) que resuma esto: '{request.prompt}'. Solo devuelve el título, nada más."
            title_payload = {"model": request.model, "prompt": title_prompt, "stream": False}
            title_res = requests.post(f"{ollama_url}/api/generate", json=title_payload)
            if title_res.status_code == 200:
                title = title_res.json().get("response", "Nueva conversación").strip().replace('"', '')
                redis_client.set(f"session:{session_id}:description", title)
        except Exception as e:
            print(f"Error generando título: {e}")

    # Recuperar el contexto si existe un session_id
    context = None
    cached_context = redis_client.get(f"session:{session_id}:context")
    if cached_context:
        context = json.loads(cached_context)
    
    def generate():
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": True
        }
        if context:
            payload["context"] = context
            
        with requests.post(f"{ollama_url}/api/generate", json=payload, stream=True) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    json_response = json.loads(line.decode('utf-8'))
                    if "response" in json_response:
                        yield json_response["response"]
                    
                    # Guardar el contexto al finalizar la respuesta
                    if json_response.get("done"):
                        if "context" in json_response:
                            redis_client.set(f"session:{session_id}:context", json.dumps(json_response["context"]))
            
            # Al final del stream, enviamos el session_id para que el cliente sepa cuál usar
            yield json.dumps({"session_id": session_id})

    return StreamingResponse(generate(), media_type="text/plain")
