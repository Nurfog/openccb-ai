# main.py
# Este será el punto de entrada para nuestra API.

import os
import json
import requests
import redis
import uuid
import io
import boto3
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from passlib.context import CryptContext
from typing import List, Optional
from pypdf import PdfReader
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, DateTime
from sqlalchemy import or_
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

# Esperar a que la base de datos esté lista
import time
max_retries = 30
for i in range(max_retries):
    try:
        with engine.connect() as conn:
            print("Conexión a la base de datos exitosa")
            break
    except Exception as e:
        print(f"Esperando a la base de datos... intento {i+1}/{max_retries}")
        time.sleep(2)
else:
    raise Exception("No se pudo conectar a la base de datos después de varios intentos")

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

class KnowledgePage(Base):
    __tablename__ = "knowledge_pages"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    s3_key = Column(String, index=True)
    page_number = Column(Integer)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

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
    model: str = "gpt-oss:20b"  # Asegúrate de tener este modelo descargado en Ollama
    session_id: Optional[str] = None # Identificador opcional
    use_kb: bool = False # Usar base de conocimiento

class S3SyncRequest(BaseModel):
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    bucket_name: str

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

@app.post("/s3/sync")
def sync_s3(request: S3SyncRequest, db: Session = Depends(get_db)):
    s3 = boto3.client('s3', 
                      aws_access_key_id=request.aws_access_key_id, 
                      aws_secret_access_key=request.aws_secret_access_key, 
                      region_name=request.aws_region)
    
    try:
        response = s3.list_objects_v2(Bucket=request.bucket_name)
        if 'Contents' not in response:
            return {"message": "Bucket vacío o sin acceso"}
            
        count = 0
        for obj in response['Contents']:
            key = obj['Key']
            # Solo procesar PDFs por ahora
            if not key.lower().endswith('.pdf'): continue
            
            # Verificar si ya existe alguna página de este documento para no procesarlo de nuevo
            if db.query(KnowledgePage).filter(KnowledgePage.s3_key == key).first():
                continue
                
            # Descargar y procesar
            file_obj = io.BytesIO()
            s3.download_fileobj(request.bucket_name, key, file_obj)
            file_obj.seek(0)
            pdf = PdfReader(file_obj)
            
            # Procesar página por página
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    doc = KnowledgePage(filename=key.split('/')[-1], s3_key=key, page_number=i+1, content=text)
                    db.add(doc)
                    count += 1
        
        db.commit()
        return {"message": f"Sincronizadas {count} páginas nuevas desde S3"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error S3: {str(e)}")

@app.post("/local/sync")
def sync_local(db: Session = Depends(get_db)):
    base_path = "/context"
    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="Carpeta de contexto no encontrada.")
    
    # Extensiones de archivos de código y texto a procesar
    allowed_extensions = {'.py', '.md', '.txt', '.yml', '.yaml', '.sh', '.json', '.sql', '.js', '.html', '.css', '.env.example', '.dockerfile'}
    # Directorios a ignorar para no ensuciar el contexto
    ignore_dirs = {'.git', '__pycache__', 'postgres_data', 'redis_data', 'ollama_data', 'venv', 'node_modules', '.idea', '.vscode'}
    
    count = 0
    files_processed = 0
    
    for root, dirs, files in os.walk(base_path):
        # Modificar dirs in-place para saltar directorios ignorados
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in allowed_extensions or file.lower() in ['dockerfile', 'makefile', 'requirements.txt']:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, base_path)
                key = f"local/{rel_path}"
                
                # Verificar si ya existe (evitar duplicados)
                # if db.query(KnowledgePage).filter(KnowledgePage.s3_key == key).first():
                #     continue
                
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read().replace('\x00', '')
                        if content.strip():
                            # Guardamos el archivo completo como página 1
                            doc = KnowledgePage(filename=rel_path, s3_key=key, page_number=1, content=content)
                            db.add(doc)
                            count += 1
                            files_processed += 1
                except Exception as e:
                    print(f"Error leyendo {file_path}: {e}")
    db.commit()
    return {"message": f"Contexto del proyecto sincronizado. {files_processed} archivos de código/texto indexados."}

@app.get("/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(KnowledgePage.filename).distinct().all()
    return [doc[0] for doc in docs]

@app.get("/documents/{filename}")
def view_document(filename: str, db: Session = Depends(get_db)):
    pages = db.query(KnowledgePage).filter(KnowledgePage.filename == filename).order_by(KnowledgePage.page_number).all()
    if not pages:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return [{"page": p.page_number, "content": p.content} for p in pages]

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
    user_msg = ChatMessage(session_id=session_id, role="user", content=request.prompt.replace('\x00', ''))
    db.add(user_msg)
    db.commit()

    # Recuperar el contexto si existe un session_id
    context = None
    cached_context = redis_client.get(f"session:{session_id}:context")
    if cached_context:
        context = json.loads(cached_context)
    
    # Lógica RAG (Búsqueda simple por palabras clave en DB)
    rag_context = ""
    if request.use_kb:
        # Buscamos documentos que contengan palabras clave del prompt (búsqueda ingenua pero funcional sin vectores)
        keywords = [w for w in request.prompt.split() if len(w) > 4] # Palabras > 4 letras
        if keywords:
            filters = [KnowledgePage.content.ilike(f"%{kw}%") for kw in keywords]
            docs = db.query(KnowledgePage).filter(or_(*filters)).limit(5).all()
            
            if docs:
                rag_context = "Instrucción: Utiliza la siguiente información de la base de conocimiento para responder. Es OBLIGATORIO que cites el documento, la ruta y la hoja (página) de donde obtuviste la información.\n\n"
                for d in docs:
                    rag_context += f"--- Documento: {d.filename} | Ruta: {d.s3_key} | Hoja: {d.page_number} ---\n{d.content[:2000]}...\n\n"

    def generate():
        full_response = ""
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": True
        }
        if context:
            payload["context"] = context
        
        if rag_context:
            payload["prompt"] = f"{rag_context}\n\nPregunta del usuario: {request.prompt}"
            
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
            elif e.response.status_code == 500:
                yield f"Error Interno (500): El servidor de IA se quedó sin memoria al intentar cargar '{request.model}'. Revisa los logs del contenedor 'ollama' con 'docker compose logs ollama' para más detalles."
            else:
                yield f"Error de IA ({e.response.status_code}): {e.response.text}"
        except Exception as e:
            yield f"Error de conexión con IA: {str(e)}"
            
        # Guardar respuesta del asistente en DB al finalizar el stream
        # Usamos una nueva sesión de DB porque estamos dentro de un generador
        with SessionLocal() as db_inner:
            ai_msg = ChatMessage(session_id=session_id, role="assistant", content=full_response.replace('\x00', ''))
            db_inner.add(ai_msg)
            db_inner.commit()

    headers = {"X-Session-Id": session_id}
    return StreamingResponse(generate(), headers=headers, media_type="text/plain")

@app.post("/analyze")
async def analyze_document(file: UploadFile = File(...), model: str = "gpt-oss:20b", query: Optional[str] = None):
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
            text += (page.extract_text() or "").replace('\x00', '')
            
        if not text.strip():
             raise HTTPException(status_code=400, detail="No se pudo extraer texto del PDF (puede ser una imagen)")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo el archivo: {str(e)}")

    # 3. Enviar a la IA para buscar temas
    # Truncamos el texto para no saturar el contexto (aprox 12k caracteres para empezar)
    truncated_text = text[:12000]
    if query:
        prompt = f"Basado únicamente en el siguiente texto, responde a la pregunta: '{query}'. Si la respuesta no está en el texto, indícalo.\n\nTEXTO:\n{truncated_text}"
    else:
        prompt = f"Analiza el siguiente documento y lista los 5 temas principales o puntos clave que se tratan en él:\n\nTEXTO:\n{truncated_text}"

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    payload = {"model": model, "prompt": prompt, "stream": False}

    try:
        response = requests.post(f"{ollama_url}/api/generate", json=payload)
        if response.status_code == 200:
            return {"result": response.json().get("response", "")}
        else:
            raise HTTPException(status_code=response.status_code, detail="Error en el motor de IA")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de conexión con IA: {str(e)}")

@app.get("/files")
def list_files(path: str = "/context"):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="La ruta no es un directorio")
    
    try:
        items = []
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            is_dir = os.path.isdir(item_path)
            items.append({
                "name": item,
                "path": item_path,
                "is_directory": is_dir,
                "size": os.path.getsize(item_path) if not is_dir else 0
            })
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listando archivos: {str(e)}")

@app.get("/file/content")
def get_file_content(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="La ruta no es un archivo")
    
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(10000)  # Limitar a 10k chars para evitar timeouts
        return {"content": content, "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo archivo: {str(e)}")
