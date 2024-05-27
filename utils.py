import os
import getpass
import json
import streamlit as st
from dotenv import load_dotenv
import google.generativeai as genai
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.chains.question_answering import load_qa_chain

from sentence_transformers import SentenceTransformer
from langchain_community.vectorstores import Pinecone as CommunityPinecone
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.chains import RetrievalQA
from pinecone import Pinecone
from FlagEmbedding import FlagModel

from langchain_community.chat_models import ChatOpenAI

from langchain.chains import ConversationChain
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate,
    MessagesPlaceholder
)
from google.generativeai.types.safety_types import HarmBlockThreshold, HarmCategory
from streamlit_chat import message

import warnings
from langchain._api import LangChainDeprecationWarning
warnings.simplefilter("ignore", category=LangChainDeprecationWarning)

# Load environment variables from .env file
st.write(
    "Has environment variables been set:",
    os.environ["OPENAI_API_KEY"] == st.secrets["OPENAI_API_KEY"],
    os.environ["GOOGLE_API_KEY"] == st.secrets["GOOGLE_API_KEY"],
    os.environ["PINECONE_API_KEY"] == st.secrets["PINECONE_API_KEY"]
)


class Pipeline:
    
    def __init__(self):
        # For the prompt template in the conversation chain
        self.PROMT_TEMPLATE = """
            As a film creator's assistant, your task is to develop highly creative, thought-provoking, and creative ideas for a film screenplay. Don't be afraid to think outside the box and surprise me with your originality. I might provide parts of an older script for inspiration. However, consider carefully if those elements truly fit the new ideas and are still effective before incorporating them. Your responses should be longer, more in-depth, and highly detailed. I want a comprehensive overview of your ideas, including a concise plot summary highlighting an synopsis that dives deeper into the story's core conflicts, turning points, and resolutions, and vivid character descriptions. Describe the overall tone and mood of the story, including the central themes and ideas and what message you want the audience to take away. Please avoid using technical script formatting like sluglines.
            
            Context:\n{context}\n
            Question:\n{question}\n

            Answer:
        """        

        # For find similar documents in vector database
        self.score_threshold = 0.4
        self.k = 5

        self.safety_settings =  {
                HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            }
        
        # Initialize chat models and Pinecone index
        self.index_name = "botgpt-ips-v2"
        self.llm = ChatOpenAI(model_name="gpt-4o", temperature=0.9)
        self.vector_store = CommunityPinecone.from_existing_index(self.index_name, OpenAIEmbeddings(model='text-embedding-3-small'))
        self.llmGe = ChatGoogleGenerativeAI(model="gemini-1.5-pro-latest", client=genai, temperature=1, safety_settings=self.safety_settings)
        
        # Initialize session state variables
        self.initialize_session_state()

        # Initialize conversation chain
        self.initialize_conversation_chain()

    def initialize_session_state(self):
        if 'responses' not in st.session_state:
            st.session_state['responses'] = ["How can I help you today?"]

        if 'requests' not in st.session_state:
            st.session_state['requests'] = []

        if 'messages' not in st.session_state:
            st.session_state['messages'] = []

        if 'buffer_memory' not in st.session_state:
            st.session_state['buffer_memory'] = ConversationBufferWindowMemory(k=100000, return_messages=True)
        if 'chat_history' not in st.session_state:
            st.session_state['chat_history'] = []

    def initialize_conversation_chain(self):
        self.system_msg_template = SystemMessagePromptTemplate.from_template(
            template = 
                """
                As a film creator's assistant, your task is to develop highly creative, thought-provoking, and creative ideas for a film screenplay. Don't be afraid to think outside the box and surprise me with your originality. I might provide parts of an older script for inspiration. However, consider carefully if those elements truly fit the new ideas and are still effective before incorporating them. Your responses should be longer, more in-depth, and highly detailed. I want a comprehensive overview of your ideas, including a concise plot summary highlighting an synopsis that dives deeper into the story's core conflicts, turning points, and resolutions, and vivid character descriptions. Describe the overall tone and mood of the story, including the central themes and ideas and what message you want the audience to take away. Please avoid using technical script formatting like sluglines.
                """
            
        )
        self.human_msg_template = HumanMessagePromptTemplate.from_template(template="{input}")
        self.prompt_template = ChatPromptTemplate.from_messages([self.system_msg_template, MessagesPlaceholder(variable_name="history"), self.human_msg_template])
        self.conversation = ConversationChain(memory=st.session_state.buffer_memory, prompt=self.prompt_template, llm=self.llm, verbose=True)
    
    # Function to find matching documents
    def find_match(self, input_text, is_rag):
        matches = ""
        if is_rag:
            result = self.vector_store.similarity_search_with_score(input_text, k=self.k)
            matches = [doc.page_content for doc, score in result if score > self.score_threshold]
        return "\n".join(matches)
    
    # Function to log reference ips
    def log_reference_ips(self, input_text, is_rag):
        reference_ips = ""
        if is_rag:
            result = self.vector_store.similarity_search_with_score(input_text, k=self.k)
            reference_ips = [doc.metadata['Title'] for doc, score in result if score > self.score_threshold]
        
        return ", ".join(list(set(reference_ips)))


    def chain_gemini(self, query):
        query = PromptTemplate(template=self.PROMT_TEMPLATE, input_variables=["context", "question"])
        chain_gemini = load_qa_chain(llm=self.llmGe, chain_type="stuff", prompt=query)
        return chain_gemini

    def user_input(self, user_question, is_rag=True):
        if is_rag:
            docs = self.vector_store.similarity_search(user_question)
        else:
            docs = ""
        chain = self.chain_gemini(user_question)
        response = chain({"input_documents": docs, "question": user_question}, return_only_outputs=True)
        return response
    
    def save_chat_history(self,chat_history, folder_name, file_name):
        folder_path = os.path.join(os.getcwd(), folder_name)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        file_path = os.path.join(folder_name, file_name)
        with open(file_path, 'w', encoding='utf-8') as f:
            for timestamp, query, response in chat_history:
                f.write(f"user | {timestamp} | {query}\n")
                f.write(f"bot | {timestamp} | {response}\n")
