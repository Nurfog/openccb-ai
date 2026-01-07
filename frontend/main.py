import streamlit as st
import requests
import json
import os

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
                ["llama3", "mistral", "gemma2", "codellama", "phi3", "tinyllama"],
                index=0,
                help="Selecciona el modelo según tu tarea. Si falla, asegúrate de descargarlo."
            )
            
            st.divider()
            st.subheader("☁️ Base de Conocimiento (S3)")
            if st.button("Sincronizar Documentos"):
                with st.spinner("Descargando e indexando desde S3..."):
                    try:
                        res = requests.post(f"{API_URL}/s3/sync")
                        if res.status_code == 200:
                            st.success(res.json().get("message"))
                        else:
                            st.error(f"Error: {res.text}")
                    except Exception as e:
                        st.error(f"Error de conexión: {e}")
            
            st.divider()
            st.subheader("📄 Analizar Documento")
            uploaded_file = st.file_uploader("Subir PDF para buscar temas", type="pdf")
            doc_query = st.text_input("Pregunta sobre el documento (Opcional)", placeholder="Ej: ¿Dónde está el procedimiento de no conformidad?")
            
            if uploaded_file is not None:
                if st.button("Analizar Documento"):
                    with st.spinner("Procesando documento..."):
                        try:
                            files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
                            params = {"model": st.session_state.current_model}
                            if doc_query:
                                params["query"] = doc_query
                            res = requests.post(f"{API_URL}/analyze", files=files, params=params)
                            
                            if res.status_code == 200:
                                st.success("Análisis completado")
                                st.info(res.json().get("result"))
                            else:
                                st.error(f"Error: {res.text}")
                        except Exception as e:
                            st.error(f"Error de conexión: {e}")
            
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
                payload = {
                    "username": st.session_state.username,
                    "prompt": prompt,
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

                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            text_chunk = chunk.decode("utf-8")
                            full_response += text_chunk
                            message_placeholder.markdown(full_response + "▌")
                    
                    message_placeholder.markdown(full_response)
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
                else:
                    st.error(f"Error del servidor: {response.status_code} - {response.text}")
            except Exception as e:
                st.error(f"Error de conexión: {e}")

def main():
    login_register_sidebar()
    
    if st.session_state.username:
        chat_interface()
    else:
        st.info("👈 Por favor, inicia sesión o regístrate en el menú lateral para comenzar.")

if __name__ == "__main__":
    main()