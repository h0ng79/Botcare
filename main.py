import os
import streamlit as st
from utils import Pipeline
from streamlit_chat import message
from streamlit_extras.stylable_container import stylable_container
from datetime import datetime
from google.cloud import storage
from google.oauth2 import service_account

# Set up the page configuration
st.set_page_config(page_title="BotGPT", layout="centered")

pipeline = Pipeline()
# st.write(st.secrets.keys())
# Load GCS credentials
credentials = service_account.Credentials.from_service_account_info(st.secrets["connections"])
# client = storage.Client(credentials=credentials, project=st.secrets["connections"]["project_id"])

def login():
    """Renders the login page and handles authentication."""
    st.markdown(
        """
        <style>
        .login-form {
            max-width: 120px;
            margin: auto;
            text-align: center;
        }
        .stButton button {
            width: 40%; 
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    with st.container():
        st.markdown('<div class="login-form">', unsafe_allow_html=True)
        
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login"):
            credentials = st.secrets.get("CREDENTIALS", {})
            if credentials.get(username) == password:
                st.session_state.authenticated = True
                st.session_state.username = username
                st.experimental_rerun()  # Force rerun after successful login
            else:
                st.error("Invalid username or password")

        st.markdown('</div>', unsafe_allow_html=True)

def logout():
    """Handles the logout process."""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.experimental_rerun()

def get_gcs_client():
    return storage.Client(credentials=credentials, project=st.secrets["connections"]["project_id"])

def load_chat_history_from_gcs(bucket_name, file_name):
    client = get_gcs_client()
    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(file_name)
    chat_history = []
    if blob.exists():
        content = blob.download_as_text()
        lines = content.splitlines()
        current_role = None
        current_timestamp = None
        current_content = []

        for line in lines:
            if line.startswith("user |") or line.startswith("bot |"):
                if current_role and current_content:
                    chat_history.append((current_role, current_timestamp, "\n".join(current_content)))
                parts = line.split(' | ', 2)
                if len(parts) == 3:
                    current_role, current_timestamp, content = parts
                    current_content = [content]
                else:
                    current_content = [line]
            else:
                current_content.append(line)
        
        if current_role and current_content:
            chat_history.append((current_role, current_timestamp, "\n".join(current_content)))
    
    return chat_history

def save_chat_history_to_gcs(chat_history, bucket_name, file_name):
    client = get_gcs_client()
    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(file_name)
    content = "\n".join([f"{role} | {timestamp} | {content}" for role, timestamp, content in chat_history])
    blob.upload_from_string(content)

def delete_chat_history_from_gcs(bucket_name, file_name):
    client = get_gcs_client()
    bucket = client.get_bucket(bucket_name)
    blob = bucket.blob(file_name)
    if blob.exists():
        blob.delete()
        st.success(f"Deleted {file_name}")

def list_chat_history_files_in_gcs(bucket_name, prefix=''):
    client = get_gcs_client()
    bucket = client.get_bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    return [blob.name for blob in blobs if blob.name.endswith('.txt')]

def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        login()
    else:
        bucket_name = "chatbotgpt1"  # Replace with your GCS bucket name

        with st.sidebar:
            st.write(f"Welcome, {st.session_state.username}!")
            if st.button("Logout"):
                logout()
            st.write("### Select Model")
            selected_model = st.session_state.get("selected_model", "ChatGPT 4o")
    
            model_options = st.radio("Model", ["ChatGPT 4o", "Gemini-Pro"], key="model_select")
            if model_options == "Gemini-Pro":
                selected_model = "Gemini-Pro"
            else:
                selected_model = "ChatGPT 4o"
    
            st.write("### Retrieve Database")
            selected_is_rag = st.session_state.get("selected_is_rag", True)
    
            is_rag_options = st.radio("RAG", ["Yes", "No"], key="is_rag")
            if is_rag_options == "Yes":
                selected_is_rag = True
            else:
                selected_is_rag = False
    
            st.write("###")
            if st.button("New Chat"):
                if selected_model == "Gemini-Pro":
                    st.session_state['requests_gemini'] = []
                    st.session_state['responses_gemini'] = []
                    st.session_state['chat_history_gemini'] = []
                else:
                    st.session_state['requests_chatgpt'] = []
                    st.session_state['responses_chatgpt'] = []
                    st.session_state['chat_history_chatgpt'] = []
                st.session_state['loaded_chat_history'] = []
    
            chat_history_filename = st.text_input("Chat History Filename", value=".txt", placeholder="Enter chat history filename")
            if chat_history_filename:
                st.session_state["chat_history_filename"] = chat_history_filename
    
            st.write("### Chat History Files")
            chat_files = list_chat_history_files_in_gcs(bucket_name)
            selected_file = st.selectbox("Select a chat history file to load", chat_files)
            
            if selected_file:
                if st.button("Load Chat History"):
                    chat_history = load_chat_history_from_gcs(bucket_name, selected_file)
                    st.session_state["loaded_chat_history"] = chat_history
                if st.button("Delete Chat History"):
                    delete_chat_history_from_gcs(bucket_name, selected_file)
                    chat_files = list_chat_history_files_in_gcs(bucket_name)
                    st.experimental_rerun()

        if "loaded_chat_history" in st.session_state and st.session_state["loaded_chat_history"]:
            st.write("### Loaded Chat History")
            for i, (role, timestamp, content) in enumerate(st.session_state["loaded_chat_history"]):
                is_user = role == "user"
                formatted_message = f"{timestamp}\n{content}"
                message(formatted_message, is_user=is_user, key=f"loaded_{role}_{i}")
    
        st.session_state["selected_model"] = selected_model
        reference_ips = ""
        if query := st.chat_input("Type your question here..."):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            reference_ips = pipeline.log_reference_ips(query, selected_is_rag)
            with st.spinner("typing..."):
                if selected_model == "Gemini-Pro":
                    response = pipeline.user_input(query, selected_is_rag)
                    response_text = response['output_text'] if isinstance(response, dict) and 'output_text' in response else str(response)
                    st.session_state.setdefault('requests_gemini', []).append((timestamp, query))
                    st.session_state.setdefault('responses_gemini', []).append((timestamp, response_text))
                    st.session_state.setdefault('chat_history_gemini', []).append((timestamp, query, response_text))
                    chat_history_filename = st.session_state.get("chat_history_filename", "chat_history_gemini.txt")
                    save_chat_history_to_gcs(st.session_state['chat_history_gemini'], bucket_name, chat_history_filename)
                else:
                    context = pipeline.find_match(query, selected_is_rag)
                    response_text = pipeline.conversation.predict(input=f"Context:\n {context} \n\n Query:\n{query}")
                    st.session_state.setdefault('requests_chatgpt', []).append((timestamp, query))
                    st.session_state.setdefault('responses_chatgpt', []).append((timestamp, response_text))
                    st.session_state.setdefault('chat_history_chatgpt', []).append((timestamp, query, response_text))
                    chat_history_filename = st.session_state.get("chat_history_filename", "chat_history_chatgpt.txt")
                    save_chat_history_to_gcs(st.session_state['chat_history_chatgpt'], bucket_name, chat_history_filename)
    
        if selected_model == "Gemini-Pro" and st.session_state.get('responses_gemini'):
            for i, ((timestamp_q, query), (timestamp_r, response)) in enumerate(zip(st.session_state['requests_gemini'], st.session_state['responses_gemini'])):
                message(f"{timestamp_q}\n{query}", is_user=True, key=f"gemini_{i}_user")
                if reference_ips: st.write(f"Reading context from these movies: {reference_ips}")
                message(f"{timestamp_r}\n{response}", key=f"gemini_{i}")
        elif selected_model == "ChatGPT 4o" and st.session_state.get('responses_chatgpt'):
            for i, ((timestamp_q, query), (timestamp_r, response)) in enumerate(zip(st.session_state['requests_chatgpt'], st.session_state['responses_chatgpt'])):
                message(f"{timestamp_q}\n{query}", is_user=True, key=f"chatgpt_{i}_user")
                if reference_ips: st.write(f"Reading context from these movies: {reference_ips}")
                message(f"{timestamp_r}\n{response}", key=f"chatgpt_{i}")

if __name__ == "__main__":
    main()
