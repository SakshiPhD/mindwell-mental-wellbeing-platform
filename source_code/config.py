"""
Configuration and Session State for MindWell application.
Contains session state initialization and constants.
"""
import streamlit as st
from engine import MultiAgentEngine

# Set to False in production to hide OTP on screen
DEMO_MODE = True


# ===================== THEME CONFIGURATION =====================
THEME_COLORS = [
    ("Midnight Purple", "linear-gradient(-45deg, #0f0c29, #302b63, #24243e, #8E2DE2, #4A00E0, #0f0c29)"),
    ("Oceanic Flow", "linear-gradient(-45deg, #0060ba, #00d2ff, #3a7bd5, #00d2ff, #0060ba)"),
    ("Aurora Borealis", "linear-gradient(-45deg, #00c6ff, #0072ff, #00d2ff, #92fe9d, #00c6ff)"),
    ("Sunset Vibes", "linear-gradient(-45deg, #ee0979, #ff6a00, #ff9a9e, #fecfef, #ee0979)"),
    ("Deep Space", "linear-gradient(-45deg, #000428, #004e92, #2c3e50, #4ca1af, #000428)"),
    ("Royal Velvet", "linear-gradient(-45deg, #141E30, #243B55, #4b6cb7, #182848, #141E30)"),
    ("Electric Dreams", "linear-gradient(-45deg, #833ab4, #fd1d1d, #fcb045, #12c2e9, #c471ed, #833ab4)"),
    ("Zen Garden", "linear-gradient(-45deg, #134E5E, #71B280, #2BC0E4, #EAECC6, #134E5E)"),
]

# Base RGB colors for each theme (used by the animated background circle)
THEME_BASE_COLORS = [
    "200, 180, 255",   # Light Lavender Purple
    "150, 210, 255",   # Light Sky Blue
    "180, 230, 255",   # Light Cyan Blue
    "255, 200, 220",   # Light Pink
    "180, 220, 255",   # Light Blue
    "200, 190, 240",   # Light Periwinkle
    "220, 180, 240",   # Light Orchid
    "180, 240, 240",   # Light Turquoise
]



def init_session_state():
    """Initialize all session state variables."""
    if "page" not in st.session_state:
        st.session_state.page = "loading"
    if "current_uid" not in st.session_state:
        st.session_state.current_uid = None
    if "user_name" not in st.session_state:
        st.session_state.user_name = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "onboard_step" not in st.session_state:
        st.session_state.onboard_step = 1
    if "ans" not in st.session_state:
        st.session_state.ans = []
    if "show_welcome" not in st.session_state:
        st.session_state.show_welcome = False
    if "login_otp" not in st.session_state:
        st.session_state.login_otp = None
    if "signup_otp" not in st.session_state:
        st.session_state.signup_otp = None
    if "login_user" not in st.session_state:
        st.session_state.login_user = None
    # Recreate engine if missing OR stale after code reload.
    # Streamlit may retain old class instances across reruns.
    if "engine" not in st.session_state or not isinstance(st.session_state.engine, MultiAgentEngine):
        st.session_state.engine = MultiAgentEngine()
    if "theme_idx" not in st.session_state:
        st.session_state.theme_idx = 0
    if "chat_title" not in st.session_state:
        st.session_state.chat_title = "New Conversation"
    if "high_risk_turn_count" not in st.session_state:
        st.session_state.high_risk_turn_count = 0
    if "onboarding_profile" not in st.session_state:
        st.session_state.onboarding_profile = {}
