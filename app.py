"""
MindWell - Mental Wellbeing Application
Entry point that orchestrates all modules.
"""
from dotenv import load_dotenv
load_dotenv()  # Load .env file BEFORE any other imports

import streamlit as st
import re

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
    # show_profile_page  # COMMENTED OUT: Profile page disabled
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
elif st.session_state.page == "trusted_adult_form":
    show_trusted_adult_form()
# COMMENTED OUT: Profile page disabled
# elif st.session_state.page == "profile":
#     show_profile_page(st.session_state.get("user_id"), st.session_state.get("user_name", "User"))
elif st.session_state.page in ("chat", "chatbot"):
    show_chatbot()
else:
    st.session_state.page = "loading"
    st.rerun()
