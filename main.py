import os
import streamlit as st
from utils import *
from streamlit_chat import message
import pyperclip
from utils import Pipeline
from streamlit_extras.stylable_container import stylable_container
from datetime import datetime

# Set up the page configuration
st.set_page_config(page_title="ChatBotCare", layout="centered")

pipeline = Pipeline()

def login():
    """Renders the login page and handles authentication."""
    # Insert your logo here
    # st.image("logo.png", use_column_width=True)
    
    st.markdown(
        """
        <style>
        .login-form {
            max-width: 100px;
            margin: auto;
            text-align: center;
        }
        .stButton button {
            width: 100%;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    with st.container():
        st.markdown('<div class="login-form">', unsafe_allow_html=True)
        st.title("Login")
        
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login"):
            credentials = st.secrets.get("CREDENTIALS", {})
            if credentials.get(username) == password:
                st.session_state.authenticated = True
                st.session_state.username = username
                # st.success("Login successful!")
            else:
                st.error("Invalid username or password")

        st.markdown('</div>', unsafe_allow_html=True)

def logout():
    """Handles the logout process."""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.success("Logged out successfully!")

# Function to load chat history from a file
def load_chat_history(file_path):
    chat_history = []
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    
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

# Function to delete chat history file
def delete_chat_history(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
        st.success(f"Deleted {file_path}")

def main():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        login()
    else:
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
                # Reset loaded chat history
                st.session_state['loaded_chat_history'] = []
    
            # New input field for the chat history file name with default value ".txt"
            chat_history_filename = st.text_input("Chat History Filename", value=".txt", placeholder="Enter chat history filename")
            if chat_history_filename:
                st.session_state["chat_history_filename"] = chat_history_filename
    
            # Display existing chat history files
            st.write("### Chat History Files")
            folder_name = st.session_state.get("folder_name", "History")
            if not os.path.exists(folder_name):
                os.makedirs(folder_name)
            chat_files = [f for f in os.listdir(folder_name) if f.endswith('.txt')]
            selected_file = st.selectbox("Select a chat history file to load", chat_files)
            
            if selected_file:
                file_path = os.path.join(folder_name, selected_file)
                if st.button("Load Chat History"):
                    chat_history = load_chat_history(file_path)
                    st.session_state["loaded_chat_history"] = chat_history
                if st.button("Delete Chat History"):
                    delete_chat_history(file_path)
                    # Update chat files list after deletion
                    chat_files = [f for f in os.listdir(folder_name) if f.endswith('.txt')]
                    st.experimental_rerun()

        # Display loaded chat history
        if "loaded_chat_history" in st.session_state and st.session_state["loaded_chat_history"]:
            st.write("### Loaded Chat History")
            for i, (role, timestamp, content) in enumerate(st.session_state["loaded_chat_history"]):
                is_user = role == "user"
                formatted_message = f"{timestamp}\n{content}"
                message(formatted_message, is_user=is_user, key=f"loaded_{role}_{i}")
    
    
            # Store the selected model in session state
            st.session_state["selected_model"] = selected_model
       # Text input section
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
                    folder_name = st.session_state.get("folder_name", "History")
                    chat_history_filename = st.session_state.get("chat_history_filename", "chat_history_gemini.txt")
                    pipeline.save_chat_history(st.session_state['chat_history_gemini'], folder_name, chat_history_filename)
                else:
                    context = pipeline.find_match(query, selected_is_rag)
                    response_text = pipeline.conversation.predict(input=f"Context:\n {context} \n\n Query:\n{query}")
                    st.session_state.setdefault('requests_chatgpt', []).append((timestamp, query))
                    st.session_state.setdefault('responses_chatgpt', []).append((timestamp, response_text))
                    st.session_state.setdefault('chat_history_chatgpt', []).append((timestamp, query, response_text))
                    folder_name = st.session_state.get("folder_name", "History")
                    chat_history_filename = st.session_state.get("chat_history_filename", "chat_history_chatgpt.txt")
                    pipeline.save_chat_history(st.session_state['chat_history_chatgpt'], folder_name, chat_history_filename)
    
        # Response display section
        if selected_model == "Gemini-Pro" and st.session_state.get('responses_gemini'):
            for i, ((timestamp_q, query), (timestamp_r, response)) in enumerate(zip(st.session_state['requests_gemini'], st.session_state['responses_gemini'])):
                message(f"{timestamp_q}\n{query}", is_user=True, key=f"gemini_{i}_user")
                message(f"{timestamp_r}\n{response}", key=f"gemini_{i}")
                copy_button = st.button(f"📋", key=f"copy_response_gemini_{i}")
                if reference_ips: st.write(f"Reading context from these movies: {reference_ips}")
                if copy_button:
                    pyperclip.copy(response)
                    st.success("Response copied to clipboard!")
        elif selected_model == "ChatGPT 4o" and st.session_state.get('responses_chatgpt'):
            for i, ((timestamp_q, query), (timestamp_r, response)) in enumerate(zip(st.session_state['requests_chatgpt'], st.session_state['responses_chatgpt'])):
                message(f"{timestamp_q}\n{query}", is_user=True, key=f"chatgpt_{i}_user")
                message(f"{timestamp_r}\n{response}", key=f"chatgpt_{i}")
                copy_button = st.button(f"📋", key=f"copy_response_chatgpt_{i}")
                if reference_ips: st.write(f"Reading context from these movies: {reference_ips}")
                if copy_button:
                    pyperclip.copy(response)
                    st.success("Response copied to clipboard!")

if __name__ == "__main__":
    main()
