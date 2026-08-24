"""
MindWell - Mental Wellbeing Application
Entry point for Streamlit application
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env file BEFORE any other imports

import streamlit as st
import re

# Opt-in only: activates LangSmith tracing if real credentials are configured,
# otherwise the app runs exactly as it did with no tracing code at all. Must
# only ever trace synthetic/test conversations until a redaction/consent/
# retention policy exists — see tracing.py's module docstring.
from tracing import configure_tracing
configure_tracing(environment="development")

# Configure page first (must be first Streamlit command)
st.set_page_config(
    page_title="MindWell",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🧠"
)

# Import modules
from config import init_session_state
from styles import load_css
from pages import (
    show_loading_page,
    show_welcome_page,
    show_auth_choice,
    show_login_page,
    show_signup_page,
    show_trusted_adult_form,
    show_chatbot,
)

from database import initialize_database

# Initialize session state
init_session_state()

# Initialize database tables
initialize_database()

# Load base CSS
load_css()

# Route to appropriate page
if st.session_state.page == "loading":
    show_loading_page()
elif st.session_state.page == "welcome":
    show_welcome_page()
elif st.session_state.page == "auth_choice":
    show_auth_choice()
elif st.session_state.page == "login":
    show_login_page()
elif st.session_state.page == "signup":
    show_signup_page()
elif st.session_state.page == "trusted_adult":
    show_trusted_adult_form()
elif st.session_state.page == "chat":
    show_chatbot()
else:
    show_loading_page()
