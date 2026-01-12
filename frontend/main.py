import streamlit as st
import requests
import json
import os
import time

# Configuración
API_URL = os.getenv("API_URL", "http://api:8000")
st.set_page_config(page_title="OpenCCB AI", page_icon="🤖", layout="wide")

# Estilos CSS personalizados
st.markdown("""
<style>
    .stChatMessage { padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# Inicializar estado de sesión
if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "current_model" not in st.session_state:
    st.session_state.current_model = "llama3"
if "use_kb" not in st.session_state:
    st.session_state.use_kb = False

def login_register_sidebar():
    with st.sidebar:
        st.title("🔐 Acceso")
        tab1, tab2 = st.tabs(["Login", "Registro"])
        
        with tab1:
            with st.form("login_form"):
                l_user = st.text_input("Usuario")
                l_pass = st.text_input("Contraseña", type="password", max_chars=60, help="Máximo 60 caracteres para evitar errores de encriptación.")
                submit_login = st.form_submit_button("Iniciar Sesión", type="primary")

            if submit_login:
                try:
                    res = requests.post(f"{API_URL}/login", json={"username": l_user.strip(), "password": l_pass.strip()})
                    if res.status_code == 200:
                        st.session_state.token = res.json().get("access_token") # Ajustar según tu API
                        st.session_state.username = l_user.strip()
                        st.success("¡Bienvenido!")
                        st.rerun()
                    else:
                        st.error("Credenciales inválidas")
                except Exception as e:
                    st.error(f"Error de conexión: {e}")

        with tab2:
            with st.form("register_form"):
                r_user = st.text_input("Usuario")
                r_pass = st.text_input("Contraseña", type="password", max_chars=60, help="Máximo 60 caracteres.")
                submit_register = st.form_submit_button("Registrarse")

            if submit_register:
                if not r_user or not r_pass:
                    st.error("Por favor completa todos los campos.")
                else:
                    try:
                        res = requests.post(f"{API_URL}/register", json={"username": r_user.strip(), "password": r_pass.strip()})
                        if res.status_code == 200:
                            st.success("Usuario creado. Por favor inicia sesión.")
                        else:
                            try:
                                st.error(f"Error: {res.json().get('detail', res.text)}")
                            except:
                                st.error(f"Error ({res.status_code}): {res.text}")
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")

        if st.session_state.username:
            st.divider()
            st.write(f"Conectado como: **{st.session_state.username}**")
            
            # Selector de modelo
            st.session_state.current_model = st.selectbox(
                "Modelo de IA",
                ["gpt-oss:20b", "llama3", "mistral", "gemma2", "codellama", "phi3", "tinyllama"],
                index=0,
                help="Selecciona el modelo según tu tarea. Si falla, asegúrate de descargarlo."
            )
            
            st.divider()
            st.subheader("☁️ Base de Conocimiento (S3)")
            
            with st.expander("Configuración AWS"):
                aws_key = st.text_input("AWS Access Key", type="password")
                aws_secret = st.text_input("AWS Secret Key", type="password")
                aws_region = st.text_input("AWS Region", value="us-east-2")
                bucket_name = st.text_input("Bucket Name")

            if st.button("Sincronizar Documentos"):
                with st.spinner("Descargando e indexando desde S3..."):
                    try:
                        payload = {
                            "aws_access_key_id": aws_key,
                            "aws_secret_access_key": aws_secret,
                            "aws_region": aws_region,
                            "bucket_name": bucket_name
                        }
                        res = requests.post(f"{API_URL}/s3/sync", json=payload)
                        if res.status_code == 200:
                            st.success(res.json().get("message"))
                        else:
                            st.error(f"Error: {res.text}")
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")
            
            st.divider()
            st.subheader("📂 Contexto del Proyecto")
            st.caption("Aprender del código fuente y archivos locales.")
            
            if st.button("Sincronizar Proyecto Local"):
                with st.spinner("Leyendo estructura de archivos..."):
                    try:
                        res = requests.post(f"{API_URL}/local/sync")
                        if res.status_code == 200:
                            st.success(res.json().get("message"))
                        else:
                            st.error(f"Error: {res.text}")
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")

            st.divider()
            st.subheader("🔍 Explorar Archivos")
            st.caption("Selecciona archivos para incluir en el contexto del chat.")
            
            # Estado para archivos seleccionados
            if "selected_dirs" not in st.session_state:
                st.session_state.selected_dirs = []
            if "selected_files" not in st.session_state:
                st.session_state.selected_files = []
            if "expand_all" not in st.session_state:
                st.session_state.expand_all = False
            
            # Función para obtener todas las carpetas recursivamente
            def get_all_dirs(current_path="/context"):
                all_dirs = set()
                ignore_dirs = {'__pycache__', '.git', 'uploaded_context', 'node_modules', '.vscode', '.idea', 'venv'}
                try:
                    res = requests.get(f"{API_URL}/files", params={"path": current_path})
                    if res.status_code == 200:
                        items = res.json().get("items", [])
                        for item in items:
                            if item["is_directory"]:
                                if item["name"] not in ignore_dirs:
                                    all_dirs.add(item["path"])
                                    all_dirs.update(get_all_dirs(item["path"]))
                except Exception as e:
                    st.error(f"Error obteniendo carpetas: {e}")
                return all_dirs
            
            # Checkbox para seleccionar todas las carpetas
            if st.button("Seleccionar todas las carpetas"):
                with st.spinner("Explorando todas las carpetas..."):
                    all_dirs = get_all_dirs()
                st.success(f"Carpetas encontradas: {len(all_dirs)}")
                st.session_state.selected_dirs = list(set(st.session_state.selected_dirs).union(all_dirs))
                st.info(f"Total carpetas seleccionadas: {len(st.session_state.selected_dirs)}")
                st.session_state.expand_all = True
                st.rerun()
            
            # Función para mostrar árbol de archivos
            def display_file_tree(current_path="/context", level=0):
                ignore_dirs = {'__pycache__', '.git', 'uploaded_context', 'node_modules', '.vscode', '.idea', 'venv'}
                try:
                    res = requests.get(f"{API_URL}/files", params={"path": current_path})
                    if res.status_code == 200:
                        items = res.json().get("items", [])
                        for item in sorted(items, key=lambda x: (not x["is_directory"], x["name"])):
                            if item["is_directory"] and item["name"] in ignore_dirs:
                                continue
                            indent = "  " * level
                            if item["is_directory"]:
                                dir_checked = item["path"] in st.session_state.selected_dirs
                                with st.expander(f"{indent}📁 {item['name']}", expanded=st.session_state.expand_all):
                                    # Checkbox para la carpeta
                                    if st.checkbox(f"Seleccionar carpeta {item['name']}", value=dir_checked, key=f"dir_{item['path']}"):
                                        if item["path"] not in st.session_state.selected_dirs:
                                            st.session_state.selected_dirs.append(item["path"])
                                    else:
                                        if item["path"] in st.session_state.selected_dirs:
                                            st.session_state.selected_dirs.remove(item["path"])
                                    display_file_tree(item["path"], level + 1)
                            else:
                                checked = item["path"] in st.session_state.selected_files
                                if st.checkbox(f"{indent}📄 {item['name']}", value=checked, key=item["path"]):
                                    if item["path"] not in st.session_state.selected_files:
                                        st.session_state.selected_files.append(item["path"])
                                else:
                                    if item["path"] in st.session_state.selected_files:
                                        st.session_state.selected_files.remove(item["path"])
                    else:
                        st.error(f"Error cargando archivos: {res.text}")
                except Exception as e:
                    st.error(f"Error de conexión: {e}")
            
            display_file_tree()
            
            if st.session_state.selected_dirs or st.session_state.selected_files:
                st.write(f"Carpetas seleccionadas: {len(st.session_state.selected_dirs)} | Archivos seleccionados: {len(st.session_state.selected_files)}")
                if st.button("Limpiar Selección"):
                    st.session_state.selected_dirs = []
                    st.session_state.selected_files = []
                    st.session_state.expand_all = False
                    st.rerun()
            else:
                st.write("No hay archivos seleccionados.")

            st.divider()
            st.subheader("📁 Subir Archivos/Carpetas")
            st.caption("Arrastra y suelta archivos o carpetas aquí para añadirlos al contexto.")
            
            uploaded_files = st.file_uploader(
                "Subir archivos",
                accept_multiple_files=True,
                type=None,  # Acepta todos los tipos
                help="Puedes seleccionar múltiples archivos o arrastrarlos aquí."
            )
            
            if uploaded_files:
                st.success(f"Archivos subidos: {len(uploaded_files)}")
                for file in uploaded_files:
                    # Guardar en session_state o procesar
                    file_content = file.read().decode('utf-8', errors='ignore')
                    # Aquí podrías añadir lógica para indexar o usar directamente
                    st.text_area(f"Contenido de {file.name}", file_content[:500], height=100)
            
            # Opción para carpetas (limitado por navegador)
            st.caption("Nota: Los navegadores modernos permiten arrastrar carpetas, pero Streamlit tiene limitaciones. Usa la exploración de archivos locales arriba para mejor control.")
            
            if st.button("Cerrar Sesión"):
                st.session_state.token = None
                st.session_state.username = None
                st.session_state.messages = []
                st.session_state.session_id = None
                st.rerun()

def chat_interface():
    st.title("🤖 OpenCCB AI Assistant")
    
    # Mostrar historial
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Checkbox para activar RAG
    st.session_state.use_kb = st.checkbox("🔍 Buscar en Base de Conocimiento", value=st.session_state.use_kb)

    # Input de usuario
    if prompt := st.chat_input("Escribe tu mensaje..."):
        # Guardar y mostrar mensaje usuario
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Respuesta del asistente (Streaming)
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            
            try:
                # Indicadores de tarea
                status_placeholder = st.empty()
                status_placeholder.info("📝 Preparando contexto de archivos seleccionados...")
                
                # Obtener contenido de archivos seleccionados
                context_files = ""
                selected_files = list(st.session_state.selected_files)
                
                # Expandir carpetas seleccionadas a archivos
                def expand_dir_to_files(dir_path):
                    files = []
                    try:
                        res = requests.get(f"{API_URL}/files", params={"path": dir_path})
                        if res.status_code == 200:
                            items = res.json().get("items", [])
                            for item in items:
                                if item["is_directory"]:
                                    files.extend(expand_dir_to_files(item["path"]))
                                else:
                                    files.append(item["path"])
                    except Exception as e:
                        st.error(f"Error expandiendo {dir_path}: {e}")
                    return files
                
                for dir_path in st.session_state.selected_dirs:
                    selected_files.extend(expand_dir_to_files(dir_path))
                
                selected_files = list(set(selected_files))  # Remover duplicados
                
                if len(selected_files) > 20:
                    st.warning(f"Demasiados archivos seleccionados ({len(selected_files)}). Limitando a 20 para evitar timeouts.")
                    selected_files = selected_files[:20]
                
                if selected_files:
                    status_placeholder.info("📂 Leyendo contenido de archivos...")
                    context_files = "Contexto de archivos seleccionados:\n"
                    for file_path in selected_files:
                        try:
                            res = requests.get(f"{API_URL}/file/content", params={"path": file_path})
                            if res.status_code == 200:
                                content = res.json().get("content", "")
                                context_files += f"\n--- Archivo: {file_path} ---\n{content[:2000]}...\n"  # Limitar a 2000 chars por archivo
                            else:
                                context_files += f"\n--- Archivo: {file_path} ---\nError cargando contenido.\n"
                        except Exception as e:
                            context_files += f"\n--- Archivo: {file_path} ---\nError: {str(e)}\n"
                
                status_placeholder.info("🤖 Enviando consulta a la IA...")
                
                payload = {
                    "username": st.session_state.username,
                    "prompt": prompt + (f"\n\n{context_files}" if context_files else ""),
                    "session_id": st.session_state.session_id,
                    "model": st.session_state.current_model,
                    "use_kb": st.session_state.use_kb
                }
                
                # Petición con streaming
                response = requests.post(f"{API_URL}/chat", json=payload, stream=True)
                
                if response.status_code == 200:
                    # Actualizar el session_id desde el header de la respuesta
                    new_session_id = response.headers.get("X-Session-Id")
                    if new_session_id:
                        st.session_state.session_id = new_session_id

                    status_placeholder.info("💭 Generando respuesta...")
                    
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            text_chunk = chunk.decode("utf-8")
                            full_response += text_chunk
                            message_placeholder.markdown(full_response + "▌")
                    
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                    
                    status_placeholder.success("✅ Respuesta completada")
                    status_placeholder.empty()  # Limpiar
                    
                else:
                    st.error(f"Error del servidor: {response.status_code} - {response.text}")
            except Exception as e:
                st.error(f"Error de conexión: {e}")

def get_all_files_flat(current_path="/context"):
    files = []
    try:
        res = requests.get(f"{API_URL}/files", params={"path": current_path})
        if res.status_code == 200:
            items = res.json().get("items", [])
            for item in items:
                if item["is_directory"]:
                    if item["name"] not in {'.git', '__pycache__', 'node_modules', 'venv', '.idea', '.vscode'}:
                        files.extend(get_all_files_flat(item["path"]))
                else:
                    files.append(item["path"])
    except:
        pass
    return files

def editor_interface():
    st.header("📝 Editor de Archivos")
    
    col1, col2, col3 = st.columns([1, 3, 2])
    
    with col1:
        st.subheader("Explorador")
        if st.button("🔄 Recargar"):
            st.rerun()
            
        all_files = get_all_files_flat()
        # Mapeo para mostrar rutas relativas limpias
        display_map = {f.replace("/context/", ""): f for f in all_files}
        display_keys = sorted(list(display_map.keys()))
        
        selected_key = st.radio("Archivos", display_keys, label_visibility="collapsed") if display_keys else None
        
        st.divider()
        st.caption("Crear Nuevo")
        new_name = st.text_input("Nombre (ej: src/test.py)")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("📄 Archivo"):
                if new_name:
                    requests.post(f"{API_URL}/file/write", json={"path": new_name, "content": ""})
                    st.rerun()
        with c2:
            if st.button("📁 Carpeta"):
                if new_name:
                    requests.post(f"{API_URL}/file/mkdir", json={"path": new_name})
                    st.rerun()
    
    current_content = ""

    with col2:
        if selected_key:
            full_path = display_map[selected_key]
            st.subheader(f"Editando: {selected_key}")
            
            # Cargar contenido solo si cambia el archivo seleccionado
            if "editor_file" not in st.session_state or st.session_state.editor_file != full_path:
                res = requests.get(f"{API_URL}/file/content", params={"path": full_path})
                if res.status_code == 200:
                    st.session_state.editor_content = res.json().get("content", "")
                    st.session_state.editor_file = full_path
                    # Resetear el widget de texto para que tome el nuevo valor
                    if "code_editor" in st.session_state:
                        del st.session_state.code_editor
                else:
                    st.session_state.editor_content = ""
            
            new_content = st.text_area("Contenido", value=st.session_state.editor_content, height=600, key="code_editor")
            current_content = new_content
            
            b1, b2 = st.columns([1, 5])
            with b1:
                if st.button("💾 Guardar", type="primary"):
                    res = requests.post(f"{API_URL}/file/write", json={"path": selected_key, "content": new_content})
                    if res.status_code == 200:
                        st.success("Guardado!")
                        st.session_state.editor_content = new_content
                    else:
                        st.error(res.text)
            with b2:
                if st.button("🗑️ Eliminar"):
                    requests.delete(f"{API_URL}/file/delete", params={"path": selected_key})
                    if "editor_file" in st.session_state: del st.session_state.editor_file
                    st.rerun()
        else:
            st.info("Selecciona un archivo para editar.")

    with col3:
        if selected_key:
            st.subheader("🤖 Copilot")
            
            # Historial de chat del editor
            if "editor_messages" not in st.session_state:
                st.session_state.editor_messages = []
            
            # Contenedor con scroll para el chat
            chat_container = st.container(height=600)
            with chat_container:
                for msg in st.session_state.editor_messages:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
            
            # Input de chat
            if prompt := st.chat_input("Pregunta sobre tu código...", key="editor_chat_input"):
                st.session_state.editor_messages.append({"role": "user", "content": prompt})
                with chat_container:
                    with st.chat_message("user"):
                        st.markdown(prompt)
                    
                    with st.chat_message("assistant"):
                        msg_placeholder = st.empty()
                        full_response = ""
                        
                        # Construir contexto con el código actual
                        context_prompt = f"Actúa como un asistente de programación (Copilot). El usuario está editando el archivo: '{selected_key}'.\n"
                        context_prompt += f"Contenido del código:\n```\n{current_content}\n```\n\n"
                        context_prompt += f"Pregunta del usuario: {prompt}"
                        
                        payload = {
                            "username": st.session_state.username,
                            "prompt": context_prompt,
                            "session_id": st.session_state.session_id,
                            "model": st.session_state.current_model,
                            "use_kb": False
                        }
                        
                        try:
                            response = requests.post(f"{API_URL}/chat", json=payload, stream=True)
                            if response.status_code == 200:
                                for chunk in response.iter_content(chunk_size=1024):
                                    if chunk:
                                        full_response += chunk.decode("utf-8")
                                        msg_placeholder.markdown(full_response + "▌")
                                msg_placeholder.markdown(full_response)
                                st.session_state.editor_messages.append({"role": "assistant", "content": full_response})
                            else:
                                st.error(f"Error: {response.text}")
                        except Exception as e:
                            st.error(f"Error: {e}")

def main():
    login_register_sidebar()
    
    if st.session_state.username:
        tab1, tab2 = st.tabs(["💬 Chat con IA", "📝 Editor de Código"])
        with tab1:
            chat_interface()
        with tab2:
            editor_interface()
    else:
        st.info("👈 Por favor, inicia sesión o regístrate en el menú lateral para comenzar.")

if __name__ == "__main__":
    main()