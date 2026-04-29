"""
CSS Styling for MindWell application.
Contains all custom CSS styling for the application.
"""
import streamlit as st
import base64
import os
from config import THEME_COLORS, THEME_BASE_COLORS


def load_css():
    """Load custom CSS for all pages with dynamic background theme"""
    # Get current theme from session state
    theme_idx = st.session_state.get('theme_idx', 0)
    if theme_idx >= len(THEME_COLORS):
        theme_idx = 0
    
    _, theme_gradient = THEME_COLORS[theme_idx]
    
    # Get theme base color for the animated blobs
    if theme_idx >= len(THEME_BASE_COLORS):
        theme_idx = 0
    theme_rgb = THEME_BASE_COLORS[theme_idx]

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    * {{ font-family: 'Inter', 'Poppins', sans-serif; }}
    
    /* WAVY CIRCULAR BLOB ANIMATION */
    @keyframes blob-orbit-1 {{
        0%   {{ transform: translate(0, 0) rotate(0deg) scale(1); }}
        25%  {{ transform: translate(120px, -80px) rotate(90deg) scale(1.15); }}
        50%  {{ transform: translate(-60px, -160px) rotate(180deg) scale(0.9); }}
        75%  {{ transform: translate(-140px, 40px) rotate(270deg) scale(1.1); }}
        100% {{ transform: translate(0, 0) rotate(360deg) scale(1); }}
    }}
    
    @keyframes blob-orbit-2 {{
        0%   {{ transform: translate(0, 0) rotate(0deg) scale(1); }}
        25%  {{ transform: translate(-100px, 120px) rotate(-90deg) scale(1.2); }}
        50%  {{ transform: translate(80px, 60px) rotate(-180deg) scale(0.85); }}
        75%  {{ transform: translate(150px, -100px) rotate(-270deg) scale(1.05); }}
        100% {{ transform: translate(0, 0) rotate(-360deg) scale(1); }}
    }}
    
    @keyframes blob-orbit-3 {{
        0%   {{ transform: translate(0, 0) rotate(0deg) scale(1.1); }}
        33%  {{ transform: translate(100px, 100px) rotate(120deg) scale(0.9); }}
        66%  {{ transform: translate(-120px, -50px) rotate(240deg) scale(1.2); }}
        100% {{ transform: translate(0, 0) rotate(360deg) scale(1.1); }}
    }}
    
    @keyframes blob-orbit-4 {{
        0%   {{ transform: translate(0, 0) rotate(0deg) scale(0.95); }}
        20%  {{ transform: translate(-80px, -120px) rotate(72deg) scale(1.1); }}
        40%  {{ transform: translate(100px, -60px) rotate(144deg) scale(1.05); }}
        60%  {{ transform: translate(60px, 130px) rotate(216deg) scale(0.9); }}
        80%  {{ transform: translate(-110px, 80px) rotate(288deg) scale(1.15); }}
        100% {{ transform: translate(0, 0) rotate(360deg) scale(0.95); }}
    }}
    
    @keyframes hue-cycle {{
        0%   {{ filter: hue-rotate(0deg); }}
        100% {{ filter: hue-rotate(360deg); }}
    }}
    
    @keyframes wave-pulse {{
        0%, 100% {{ border-radius: 42% 58% 60% 40% / 45% 55% 45% 55%; }}
        25%      {{ border-radius: 55% 45% 40% 60% / 60% 40% 55% 45%; }}
        50%      {{ border-radius: 40% 60% 55% 45% / 50% 50% 40% 60%; }}
        75%      {{ border-radius: 60% 40% 45% 55% / 40% 60% 50% 50%; }}
    }}

    .stApp {{
        background: #0a0a1a !important;
        color: #FFFFFF !important;
        position: relative;
        overflow: hidden;
        min-height: 100vh;
    }}
    
    /* Animated wavy blobs with circular motion and changing colors */
    .stApp::before {{
        content: "" !important;
        display: block !important;
        position: fixed !important;
        top: -20%;
        left: -10%;
        width: 60vw;
        height: 60vw;
        background: radial-gradient(circle, rgba({theme_rgb}, 0.6), rgba({theme_rgb}, 0.4), transparent 70%) !important;
        animation: blob-orbit-1 18s ease-in-out infinite, hue-cycle 12s linear infinite, wave-pulse 8s ease-in-out infinite !important;
        pointer-events: none;
        z-index: 0;
        filter: blur(80px);
    }}
    
    .stApp::after {{
        content: "" !important;
        display: block !important;
        position: fixed !important;
        bottom: -15%;
        right: -10%;
        width: 55vw;
        height: 55vw;
        background: radial-gradient(circle, rgba({theme_rgb}, 0.5), rgba({theme_rgb}, 0.3), transparent 70%) !important;
        animation: blob-orbit-2 22s ease-in-out infinite, hue-cycle 15s linear infinite reverse, wave-pulse 10s ease-in-out infinite reverse !important;
        pointer-events: none;
        z-index: 0;
        filter: blur(90px);
    }}
    
    /* Main container overlay - light so content is visible */
    .main {{
        background: rgba(10, 10, 26, 0.25) !important;
        position: relative;
        z-index: 1;
    }}

    /* LOADING PAGE */
    @keyframes slideBounce {{
        0% {{ transform: translateY(-150%); opacity: 0; }}
        60% {{ transform: translateY(30px); opacity: 1; }}
        80% {{ transform: translateY(-15px); }}
        100% {{ transform: translateY(0); opacity: 1; }}
    }}
    
    @keyframes glow {{
        0%, 100% {{ text-shadow: 0 0 20px rgba(82, 113, 255, 0.5), 0 0 40px rgba(82, 113, 255, 0.3); }}
        50% {{ text-shadow: 0 0 30px rgba(82, 113, 255, 0.8), 0 0 60px rgba(82, 113, 255, 0.5); }}
    }}

    .loading-container {{
        display: flex; 
        justify-content: center; 
        align-items: center; 
        height: 100vh;
        font-size: 10rem;
    }}

    .loading-text {{
        color: #FFFFFF !important; 
        font-weight: 900;
        letter-spacing: 3px;
        animation: slideBounce 1.5s ease-out forwards, glow 2s ease-in-out infinite;
        text-shadow: 0 0 30px rgba(82, 113, 255, 0.6);
    }}

    /* WELCOME PAGE */
    .welcome-container {{
        display: flex; 
        flex-direction: column; 
        align-items: center;
        justify-content: center; 
        text-align: center;
        width: 100%;
        padding-top: 15vh;
        background: rgba(15, 12, 41, 0.5);
        border-radius: 20px;
        padding: 40px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(82, 113, 255, 0.3);
    }}
    
    .welcome-container h1, .welcome-container h2, .welcome-container p {{
        color: #FFFFFF !important;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
    }}

    /* BUTTONS - No word breaks */
    div.stButton > button {{
        background: linear-gradient(135deg, #5271FF, #7B9AFF) !important;
        color: white !important; 
        border-radius: 50px !important; 
        padding: 12px 30px !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        border: 1px solid rgba(82, 113, 255, 0.5) !important;
        margin-top: 10px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0px 6px 20px rgba(82, 113, 255, 0.4) !important;
        cursor: pointer !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        min-width: fit-content !important;
    }}

    div.stButton > button::before {{
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: translate(-50%, -50%);
        transition: width 0.6s, height 0.6s;
    }}

    div.stButton > button:hover {{
        background: linear-gradient(135deg, #7B9AFF, #5271FF) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0px 10px 30px rgba(82, 113, 255, 0.6) !important;
    }}
    
    div.stButton > button:active {{
        transform: translateY(-1px) !important;
        box-shadow: 0px 6px 20px rgba(82, 113, 255, 0.5) !important;
    }}

    /* CHAT PAGE */
    .stApp {{ color: white; }}
    
    .chat-header {{ 
        position: sticky !important;
        top: 0 !important;
        z-index: 1000 !important;
        display: flex; 
        justify-content: space-between; 
        align-items: center; 
        background: linear-gradient(135deg, rgba(82, 113, 255, 0.15), rgba(75, 0, 130, 0.15));
        backdrop-filter: blur(20px);
        border-radius: 20px; 
        padding: 20px 30px; 
        margin-bottom: 20px; 
        border: 1.5px solid rgba(82, 113, 255, 0.4);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }}
    
    .profile-logo-right {{ 
        width: 50px; 
        height: 50px; 
        background: linear-gradient(135deg, #5271FF, #7B9AFF);
        border-radius: 50%; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        font-weight: bold;
        color: white;
        box-shadow: 0 4px 15px rgba(82, 113, 255, 0.5);
        font-size: 1.2rem;
    }}
    
    [data-testid="stChatMessageUser"] .stChatMessageContent {{ 
        background: linear-gradient(135deg, #6a11cb, #2575fc) !important; 
        border-radius: 20px 20px 5px 20px !important;
        padding: 15px 20px !important;
        box-shadow: 0 4px 15px rgba(106, 17, 203, 0.3) !important;
        border: 1px solid rgba(82, 113, 255, 0.4) !important;
    }}
    
    [data-testid="stChatMessageAssistant"] .stChatMessageContent {{ 
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.12), rgba(82, 113, 255, 0.1)) !important; 
        border-radius: 20px 20px 20px 5px !important;
        padding: 15px 20px !important;
        backdrop-filter: blur(10px) !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2) !important;
        border: 1px solid rgba(82, 113, 255, 0.3) !important;
    }}
    
    [data-testid="stChatMessage"] {{
        background: transparent !important;
    }}
    
    [data-testid="stChatInput"] {{ 
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.1), rgba(82, 113, 255, 0.08)) !important;
        border: 1px solid rgba(82, 113, 255, 0.4) !important;
        border-radius: 15px !important;
        width: 100% !important;
    }}
    
    footer {{visibility: hidden;}}
    
    /* INPUT STYLING */
    input, [data-baseweb="select"] {{
        background-color: rgba(255, 255, 255, 0.95) !important; 
        color: #1a1a1a !important; 
        border: 1.5px solid #5271FF !important; 
        border-radius: 12px !important;
        padding: 10px 15px !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
    }}

    input:focus, [data-baseweb="select"]:focus {{
        border-color: #7B9AFF !important;
        box-shadow: 0 0 20px rgba(82, 113, 255, 0.5), inset 0 0 5px rgba(82, 113, 255, 0.1) !important;
        background-color: rgba(255, 255, 255, 1) !important;
    }}
    
    input::placeholder {{
        color: rgba(0, 0, 0, 0.5) !important;
    }}

    [data-testid="stWidgetLabel"] {{ 
        color: #FFFFFF !important; 
        font-weight: 700 !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
    }}
    
    label, p, h1 {{ 
        color: #FFFFFF !important; 
        font-weight: 600 !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
    }}

    .disclaimer {{
        color: #B0C4FF;
        font-size: 0.9rem;
        margin-top: 25px;
        opacity: 0.9;
        font-weight: 500;
        text-align: center;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
    }}

    .choice-wrapper {{
        text-align: center;
        margin-top: 10vh;
        padding: 40px;
    }}

    .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, #5271FF, #7B9AFF) !important;
        border-radius: 10px !important;
        box-shadow: 0 0 15px rgba(82, 113, 255, 0.5) !important;
    }}

    /* SIDEBAR CHAT HISTORY ALIGNMENT */
    [data-testid="stSidebar"] div.stButton > button {{
        text-align: left !important;
        justify-content: flex-start !important;
        padding-left: 20px !important;
        white-space: normal !important;
        height: auto !important;
        min-height: 50px !important;
    }}

    /* Extra animated blob elements */
    .wavy-blob {{
        position: fixed;
        pointer-events: none;
        z-index: 0;
        border-radius: 50%;
    }}
    
    .wavy-blob-3 {{
        top: 40%;
        left: 50%;
        width: 50vw;
        height: 50vw;
        background: radial-gradient(circle, rgba({theme_rgb}, 0.4), rgba({theme_rgb}, 0.2), transparent 70%);
        animation: blob-orbit-3 20s ease-in-out infinite, hue-cycle 18s linear infinite, wave-pulse 12s ease-in-out infinite;
        filter: blur(85px);
    }}
    
    .wavy-blob-4 {{
        top: 10%;
        right: 30%;
        width: 45vw;
        height: 45vw;
        background: radial-gradient(circle, rgba({theme_rgb}, 0.5), rgba({theme_rgb}, 0.3), transparent 70%);
        animation: blob-orbit-4 25s ease-in-out infinite, hue-cycle 20s linear infinite reverse, wave-pulse 14s ease-in-out infinite;
        filter: blur(75px);
    }}

    </style>
    """, unsafe_allow_html=True)

    # Inject extra animated blob elements for richer wavy background
    st.markdown("""
    <div class="wavy-blob wavy-blob-3"></div>
    <div class="wavy-blob wavy-blob-4"></div>
    """, unsafe_allow_html=True)
