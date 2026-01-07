# main.py
# Este será el punto de entrada para nuestra API.

import os
import json
import requests
import redis
import uuid
import io
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from passlib.context import CryptContext
from typing import List, Optional
from pypdf import PdfReader
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime

app = FastAPI()

# Conexión a Redis para guardar el historial de conversaciones
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, db=0)

# Configuración de Base de Datos (PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Modelos de Base de Datos ---
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    sessions = relationship("ChatSession", back_populates="owner")

class ChatSession(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True) # UUID
    user_id = Column(Integer, ForeignKey("users.id"))
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("UserDB", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session")

class ChatMessage(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    role = Column(String) # user / assistant
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    session = relationship("ChatSession", back_populates="messages")

# Crear tablas
Base.metadata.create_all(bind=engine)

# Dependencia para obtener sesión de DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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
def register(user: User, db: Session = Depends(get_db)):
    # Verificar si existe en Postgres
    db_user = db.query(UserDB).filter(UserDB.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    hashed_password = pwd_context.hash(user.password)
    new_user = UserDB(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "Usuario registrado exitosamente"}

@app.post("/login")
def login(user: User, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.username == user.username).first()
    if not db_user or not pwd_context.verify(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    return {"message": "Login exitoso", "username": user.username}

@app.get("/sessions/{username}")
def get_sessions(username: str, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    return [
        {
            "id": s.id,
            "description": s.description or "Nueva conversación",
            "created_at": s.created_at
        }
        for s in user.sessions
    ]

@app.post("/chat")
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    # Validar usuario
    user = db.query(UserDB).filter(UserDB.username == request.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    # Generar session_id si no viene uno
    session_id = request.session_id if request.session_id else str(uuid.uuid4())
    
    # Verificar/Crear sesión en DB
    db_session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    is_new_session = False
    
    if not db_session:
        is_new_session = True
        db_session = ChatSession(id=session_id, user_id=user.id)
        db.add(db_session)
        db.commit()
        
        # Generar título con IA (síncrono por simplicidad)
        try:
            title_prompt = f"Genera un título muy corto (máximo 5 palabras) que resuma esto: '{request.prompt}'. Solo devuelve el título, nada más."
            title_payload = {"model": request.model, "prompt": title_prompt, "stream": False}
            title_res = requests.post(f"{ollama_url}/api/generate", json=title_payload)
            if title_res.status_code == 200:
                title = title_res.json().get("response", "Nueva conversación").strip().replace('"', '')
                db_session.description = title
                db.commit()
        except Exception as e:
            print(f"Error generando título: {e}")

    # Guardar mensaje del usuario en DB
    user_msg = ChatMessage(session_id=session_id, role="user", content=request.prompt)
    db.add(user_msg)
    db.commit()

    # Recuperar el contexto si existe un session_id
    context = None
    cached_context = redis_client.get(f"session:{session_id}:context")
    if cached_context:
        context = json.loads(cached_context)
    
    def generate():
        full_response = ""
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": True
        }
        if context:
            payload["context"] = context
            
        try:
            with requests.post(f"{ollama_url}/api/generate", json=payload, stream=True) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        json_response = json.loads(line.decode('utf-8'))
                        if "response" in json_response:
                            full_response += json_response["response"]
                            yield json_response["response"]
                        
                        # Guardar el contexto al finalizar la respuesta
                        if json_response.get("done"):
                            if "context" in json_response:
                                redis_client.set(f"session:{session_id}:context", json.dumps(json_response["context"]))
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                yield f"Error: El modelo '{request.model}' no está instalado en Ollama. Ejecuta: docker compose exec ollama ollama pull {request.model}"
            else:
                yield f"Error de IA ({e.response.status_code}): {e.response.text}"
        except Exception as e:
            yield f"Error de conexión con IA: {str(e)}"
            
        # Guardar respuesta del asistente en DB al finalizar el stream
        # Usamos una nueva sesión de DB porque estamos dentro de un generador
        with SessionLocal() as db_inner:
            ai_msg = ChatMessage(session_id=session_id, role="assistant", content=full_response)
            db_inner.add(ai_msg)
            db_inner.commit()

    headers = {"X-Session-Id": session_id}
    return StreamingResponse(generate(), headers=headers, media_type="text/plain")

@app.post("/analyze")
async def analyze_document(file: UploadFile = File(...), model: str = "llama3"):
    # 1. Validar que sea PDF
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF")

    # 2. Leer y extraer texto del PDF
    try:
        content = await file.read()
        pdf = PdfReader(io.BytesIO(content))
        text = ""
        # Extraemos texto de todas las páginas
        for page in pdf.pages:
            text += page.extract_text() or ""
            
        if not text.strip():
             raise HTTPException(status_code=400, detail="No se pudo extraer texto del PDF (puede ser una imagen)")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo el archivo: {str(e)}")

    # 3. Enviar a la IA para buscar temas
    # Truncamos el texto para no saturar el contexto (aprox 12k caracteres para empezar)
    truncated_text = text[:12000]
    prompt = f"Analiza el siguiente documento y lista los 5 temas principales o puntos clave que se tratan en él:\n\nTEXTO:\n{truncated_text}"

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    payload = {"model": model, "prompt": prompt, "stream": False}

    try:
        response = requests.post(f"{ollama_url}/api/generate", json=payload)
        if response.status_code == 200:
            return {"topics": response.json().get("response", "")}
        else:
            raise HTTPException(status_code=response.status_code, detail="Error en el motor de IA")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión con IA: {str(e)}")
