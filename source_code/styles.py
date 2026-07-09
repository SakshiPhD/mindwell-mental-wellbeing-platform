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
        background: linear-gradient(135deg, #0a0e27 0%, #1a1f4d 50%, #0f1535 100%) !important;
        color: #ffffff !important;
        position: relative;
        overflow: hidden;
        min-height: 100vh;
        padding-bottom: 0 !important;
        margin-bottom: 0 !important;
    }}

    html, body {{
        background: #000000 !important;
        margin: 0 !important;
        padding: 0 !important;
    }}
    
    /* Animated wavy blobs with circular motion and changing colors - Light version */
    .stApp::before {{
        content: "" !important;
        display: block !important;
        position: fixed !important;
        top: -20%;
        left: -10%;
        width: 60vw;
        height: 60vw;
        background: radial-gradient(circle, rgba({theme_rgb}, 0.3), rgba({theme_rgb}, 0.15), transparent 70%) !important;
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
        background: radial-gradient(circle, rgba({theme_rgb}, 0.25), rgba({theme_rgb}, 0.12), transparent 70%) !important;
        animation: blob-orbit-2 22s ease-in-out infinite, hue-cycle 15s linear infinite reverse, wave-pulse 10s ease-in-out infinite reverse !important;
        pointer-events: none;
        z-index: 0;
        filter: blur(90px);
    }}
    
    /* Main container overlay - transparent for light background */
    .main {{
        background: transparent !important;
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
        0%, 100% {{ text-shadow: 0 0 20px rgba(200, 180, 255, 0.4), 0 0 40px rgba(180, 200, 255, 0.2); }}
        50% {{ text-shadow: 0 0 30px rgba(200, 180, 255, 0.6), 0 0 60px rgba(150, 180, 255, 0.4); }}
    }}

    .loading-container {{
        display: flex; 
        justify-content: center; 
        align-items: center; 
        height: 100vh;
        font-size: 10rem;
    }}

    .loading-text {{
        color: #ffffff !important;
        font-weight: 900;
        letter-spacing: 3px;
        animation: slideBounce 1.5s ease-out forwards, glow 2s ease-in-out infinite;
        text-shadow: 0 0 30px rgba(150, 120, 255, 0.8), 0 0 60px rgba(100, 150, 255, 0.6);
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
        background: rgba(15, 21, 50, 0.8);
        border-radius: 20px;
        padding: 40px;
        backdrop-filter: blur(10px);
        border: 2px solid rgba(150, 120, 255, 0.5);
    }}

    .welcome-container h1, .welcome-container h2, .welcome-container p {{
        color: #ffffff !important;
        text-shadow: 0 0 20px rgba(150, 120, 255, 0.6), 0 2px 8px rgba(0, 0, 0, 0.5);
    }}

    /* BUTTONS - No word breaks */
    div.stButton > button {{
        background: linear-gradient(135deg, #7b68ff, #a084ff) !important;
        color: white !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
        border: 1px solid rgba(150, 120, 255, 0.4) !important;
        margin-top: 8px !important;
        margin-bottom: 5px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0px 4px 12px rgba(150, 120, 255, 0.3) !important;
        cursor: pointer !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        min-width: fit-content !important;
    }}

    div.stButton > button:hover {{
        background: linear-gradient(135deg, #9d84ff, #c4b0ff) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0px 6px 16px rgba(150, 120, 255, 0.4) !important;
    }}

    div.stButton > button:active {{
        transform: translateY(0px) !important;
        box-shadow: 0px 2px 8px rgba(150, 120, 255, 0.3) !important;
    }}

    /* CHAT PAGE */
    .stApp {{ color: #2c3e50; }}

    .chat-header {{
        position: sticky !important;
        top: 0 !important;
        z-index: 1000 !important;
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: linear-gradient(135deg, rgba(150, 120, 255, 0.2), rgba(100, 150, 255, 0.15));
        backdrop-filter: blur(20px);
        border-radius: 20px;
        padding: 20px 30px;
        margin-bottom: 20px;
        border: 2px solid rgba(150, 120, 255, 0.5);
        box-shadow: 0 8px 32px rgba(150, 120, 255, 0.25);
    }}
    
    .profile-logo-right {{
        width: 50px;
        height: 50px;
        background: linear-gradient(135deg, #7b9aff, #c4b0ff);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        color: white;
        box-shadow: 0 4px 15px rgba(180, 160, 255, 0.3);
        font-size: 1.2rem;
    }}
    
    [data-testid="stChatMessageUser"] .stChatMessageContent {{
        background: linear-gradient(135deg, #7b9aff, #a8c5ff) !important;
        border-radius: 20px 20px 5px 20px !important;
        padding: 15px 20px !important;
        box-shadow: 0 4px 15px rgba(150, 170, 255, 0.25) !important;
        border: 1px solid rgba(180, 190, 255, 0.4) !important;
        color: white !important;
    }}

    [data-testid="stChatMessageAssistant"] .stChatMessageContent {{
        background: linear-gradient(135deg, rgba(30, 40, 80, 0.9), rgba(25, 35, 70, 0.85)) !important;
        border-radius: 20px 20px 20px 5px !important;
        padding: 15px 20px !important;
        backdrop-filter: blur(10px) !important;
        box-shadow: 0 4px 20px rgba(150, 120, 255, 0.3) !important;
        border: 1.5px solid rgba(150, 120, 255, 0.4) !important;
        color: #ffffff !important;
        text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
    }}
    
    [data-testid="stChatMessage"] {{
        background: transparent !important;
    }}
    
    [data-testid="stChatInput"] {{
        background: linear-gradient(135deg, rgba(30, 40, 80, 0.95), rgba(25, 35, 70, 0.9)) !important;
        border: 2px solid rgba(150, 120, 255, 0.5) !important;
        border-radius: 15px !important;
        width: 100% !important;
        color: #ffffff !important;
        box-shadow: 0 0 20px rgba(150, 120, 255, 0.2) !important;
        padding: 12px 16px !important;
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }}

    [data-testid="stChatInput"] input {{
        background: transparent !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: none !important;
        display: block !important;
        visibility: visible !important;
    }}

    [data-testid="stChatInput"] input::placeholder {{
        color: rgba(255, 255, 255, 0.6) !important;
    }}

    /* Ensure input button is visible */
    [data-testid="stChatInput"] button {{
        display: block !important;
        visibility: visible !important;
    }}
    
    footer {{
        visibility: hidden !important;
        display: none !important;
    }}

    /* BOTTOM CHAT INPUT STRIP */
    [data-testid="stChatInputContainer"] {{
        background: #000000 !important;
        border-top: 1px solid #000000 !important;
        padding: 12px 0 !important;
        margin-bottom: 0 !important;
    }}


    .stChatInput {{
        background: #000000 !important;
    }}

    /* Chat message container */
    [data-testid="stVerticalBlock"] {{
        background: transparent !important;
    }}

    /* ENTIRE APP CONTAINER - ENSURE NO WHITE STRIPS */
    [data-testid="stAppViewContainer"] {{
        background: #000000 !important;
        padding-bottom: 0 !important;
        margin-bottom: 0 !important;
    }}

    [data-testid="stMainBlockContainer"] {{
        background: transparent !important;
        padding-bottom: 0 !important;
        border-bottom: none !important;
    }}

    /* Hide any remaining white strips at bottom */
    [data-testid="stBottomBlockContainer"],
    [data-testid="stBottomElement"] {{
        background: #000000 !important;
        border: none !important;
    }}

    /* Remove any padding from main content area */
    .stChatInput input {{
        background: rgba(30, 40, 80, 0.95) !important;
        border: 2px solid rgba(150, 120, 255, 0.5) !important;
    }}

    /* Scrollable area - ensure dark */
    [data-testid="stChatAnchor"] {{
        background: transparent !important;
    }}

    /* STREAMLIT TOOLBAR & HEADER */
    [data-testid="stToolbar"] {{
        background: linear-gradient(135deg, #0a0e27, #1a1f4d) !important;
        border-bottom: 1px solid rgba(150, 120, 255, 0.2) !important;
    }}

    [data-testid="stToolbar"] button {{
        color: #b0c4ff !important;
    }}

    [data-testid="stToolbar"] button:hover {{
        background: rgba(150, 120, 255, 0.1) !important;
    }}

    /* Streamlit header decorations */
    [data-testid="stDecoration"] {{
        display: none !important;
    }}
    
    /* INPUT STYLING */
    input, [data-baseweb="select"] {{
        background-color: rgba(30, 40, 80, 0.95) !important;
        color: #ffffff !important;
        border: 2px solid rgba(150, 120, 255, 0.5) !important;
        border-radius: 12px !important;
        padding: 10px 15px !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 0 15px rgba(150, 120, 255, 0.1) !important;
    }}

    input:focus, [data-baseweb="select"]:focus {{
        border-color: rgba(150, 120, 255, 0.8) !important;
        box-shadow: 0 0 25px rgba(150, 120, 255, 0.5), inset 0 0 5px rgba(150, 120, 255, 0.2) !important;
        background-color: rgba(40, 50, 90, 1) !important;
    }}

    input::placeholder {{
        color: rgba(255, 255, 255, 0.5) !important;
    }}

    [data-testid="stWidgetLabel"] {{
        color: #ffffff !important;
        font-weight: 700 !important;
        text-shadow: 0 0 10px rgba(150, 120, 255, 0.4);
    }}

    label, p, h1 {{
        color: #ffffff !important;
        font-weight: 600 !important;
        text-shadow: 0 0 10px rgba(150, 120, 255, 0.3);
    }}

    .disclaimer {{
        color: #b0c4ff;
        font-size: 0.9rem;
        margin-top: 25px;
        opacity: 0.9;
        font-weight: 500;
        text-align: center;
        text-shadow: 0 0 10px rgba(150, 120, 255, 0.3);
    }}

    .choice-wrapper {{
        text-align: center;
        margin-top: 10vh;
        padding: 40px;
    }}

    .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, #9d84ff, #ff80cc) !important;
        border-radius: 10px !important;
        box-shadow: 0 0 20px rgba(150, 120, 255, 0.6) !important;
    }}

    /* TOPBAR & HEADER STYLING */
    [data-testid="stAppViewContainer"] > header {{
        background: linear-gradient(135deg, #0a0e27, #1a1f4d) !important;
        border-bottom: 1px solid rgba(150, 120, 255, 0.2) !important;
    }}

    header {{
        background: linear-gradient(135deg, #0a0e27, #1a1f4d) !important;
    }}

    .stApp > header {{
        background: linear-gradient(135deg, #0a0e27, #1a1f4d) !important;
    }}

    /* SIDEBAR CHAT HISTORY ALIGNMENT */
    [data-testid="stSidebar"] div.stButton > button {{
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 8px 12px !important;
        padding-left: 12px !important;
        white-space: normal !important;
        height: auto !important;
        min-height: auto !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        background: linear-gradient(135deg, rgba(123, 104, 255, 0.3), rgba(160, 132, 255, 0.25)) !important;
        border: 1px solid rgba(150, 120, 255, 0.3) !important;
        margin-bottom: 6px !important;
        line-height: 1.3 !important;
    }}

    [data-testid="stSidebar"] div.stButton > button:hover {{
        background: linear-gradient(135deg, rgba(123, 104, 255, 0.4), rgba(160, 132, 255, 0.35)) !important;
    }}

    /* SIDEBAR STYLING */
    [data-testid="stSidebar"] {{
        background: linear-gradient(135deg, #0a0e27 0%, #1a1f4d 100%) !important;
        border-right: 1px solid rgba(150, 120, 255, 0.2) !important;
    }}

    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
        font-size: 1rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
        margin-top: 15px !important;
        margin-bottom: 10px !important;
        text-shadow: 0 0 8px rgba(150, 120, 255, 0.3) !important;
    }}

    [data-testid="stSidebar"] p {{
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        color: #b0c4ff !important;
        margin: 2px 0 !important;
    }}

    /* Sidebar Recent Chats Label */
    [data-testid="stSidebar"] [data-baseweb="tag"] {{
        font-weight: 600 !important;
        font-size: 0.95rem !important;
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
        background: radial-gradient(circle, rgba({theme_rgb}, 0.2), rgba({theme_rgb}, 0.1), transparent 70%);
        animation: blob-orbit-3 20s ease-in-out infinite, hue-cycle 18s linear infinite, wave-pulse 12s ease-in-out infinite;
        filter: blur(85px);
    }}

    .wavy-blob-4 {{
        top: 10%;
        right: 30%;
        width: 45vw;
        height: 45vw;
        background: radial-gradient(circle, rgba({theme_rgb}, 0.18), rgba({theme_rgb}, 0.08), transparent 70%);
        animation: blob-orbit-4 25s ease-in-out infinite, hue-cycle 20s linear infinite reverse, wave-pulse 14s ease-in-out infinite;
        filter: blur(75px);
    }}

    /* Floating wellness icons */
    @keyframes float-slow {{
        0%, 100% {{ transform: translateY(0px) translateX(0px); }}
        25% {{ transform: translateY(-20px) translateX(10px); }}
        50% {{ transform: translateY(-40px) translateX(-10px); }}
        75% {{ transform: translateY(-20px) translateX(15px); }}
    }}

    @keyframes float-medium {{
        0%, 100% {{ transform: translateY(0px) rotate(0deg); }}
        50% {{ transform: translateY(-30px) rotate(5deg); }}
    }}

    @keyframes float-fast {{
        0%, 100% {{ transform: translateY(0px) translateX(0px); }}
        33% {{ transform: translateY(-15px) translateX(8px); }}
        66% {{ transform: translateY(-25px) translateX(-8px); }}
    }}

    .wellness-icon {{
        position: fixed;
        z-index: 1;
        pointer-events: none;
        opacity: 0.65;
        stroke: #F5A8C8 !important;
        color: #F5A8C8;
    }}

    .icon-brain {{ animation: float-slow 15s ease-in-out infinite; }}
    .icon-heart {{ animation: float-medium 12s ease-in-out infinite 1s; }}
    .icon-lightbulb {{ animation: float-fast 10s ease-in-out infinite 2s; }}
    .icon-network {{ animation: float-slow 18s ease-in-out infinite 0.5s; }}
    .icon-chat {{ animation: float-medium 14s ease-in-out infinite 1.5s; }}
    .icon-bed {{ animation: float-fast 11s ease-in-out infinite 2.5s; }}
    .icon-cup {{ animation: float-slow 16s ease-in-out infinite 1s; }}
    .icon-meditation {{ animation: float-medium 13s ease-in-out infinite 2s; }}
    .icon-clipboard {{ animation: float-fast 12s ease-in-out infinite 0.5s; }}
    .icon-star {{ animation: float-slow 14s ease-in-out infinite 1.5s; }}
    .icon-medical {{ animation: float-fast 13s ease-in-out infinite 0.8s; }}
    .icon-sparkle {{ animation: float-medium 11s ease-in-out infinite 0.3s; }}
    .icon-dot {{ animation: float-slow 17s ease-in-out infinite 2.2s; }}
    .icon-rings {{ animation: float-fast 15s ease-in-out infinite 1.8s; }}

    .wellness-text {{
        position: fixed;
        z-index: 1;
        pointer-events: none;
        opacity: 0.25;
        color: #F5A8C8;
        font-family: 'Poppins', cursive;
        font-size: 18px;
        font-weight: 300;
        font-style: italic;
    }}

    .text-mental-1 {{ animation: float-slow 20s ease-in-out infinite 1s; }}
    .text-mental-2 {{ animation: float-medium 18s ease-in-out infinite 2.5s; }}
    .text-mental-3 {{ animation: float-fast 16s ease-in-out infinite 0.7s; }}

    .icon-pill {{ animation: float-medium 14s ease-in-out infinite 1.2s; }}
    .icon-water {{ animation: float-slow 16s ease-in-out infinite 2.8s; }}
    .icon-leaf {{ animation: float-fast 12s ease-in-out infinite 1.1s; }}
    .icon-clock {{ animation: float-medium 15s ease-in-out infinite 0.4s; }}
    .icon-smile {{ animation: float-slow 17s ease-in-out infinite 2.3s; }}
    .icon-flower {{ animation: float-fast 14s ease-in-out infinite 1.7s; }}
    .icon-hand {{ animation: float-medium 16s ease-in-out infinite 2.1s; }}
    .icon-sun {{ animation: float-slow 18s ease-in-out infinite 0.9s; }}

    </style>
    """, unsafe_allow_html=True)

    # Inject extra animated blob elements for richer wavy background
    st.markdown("""
    <div class="wavy-blob wavy-blob-3"></div>
    <div class="wavy-blob wavy-blob-4"></div>

    <!-- Floating Wellness Icons -->
    <svg class="wellness-icon icon-brain" style="width: 60px; height: 60px; top: 10%; left: 5%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 8C20 8 10 14 10 24c0 8 6 14 12 16v12c0 2 1 4 3 4h14c2 0 3-2 3-4v-12c6-2 12-8 12-16 0-10-10-16-22-16z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-heart" style="width: 50px; height: 50px; top: 25%; right: 10%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 56C32 56 8 40 8 28c0-8 6-14 12-14 4 0 8 2 10 6 2-4 6-6 10-6 6 0 12 6 12 14 0 12-24 28-24 28z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-lightbulb" style="width: 55px; height: 55px; top: 40%; left: 8%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 8c-8 0-14 6-14 14 0 6 3 11 7 13v4c0 1 1 2 2 2h10c1 0 2-1 2-2v-4c4-2 7-7 7-13 0-8-6-14-14-14zM26 42h12v2c0 1-1 2-2 2h-8c-1 0-2-1-2-2v-2z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-network" style="width: 65px; height: 65px; top: 15%; right: 20%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <circle cx="32" cy="16" r="4" stroke="#F5A8C8"/>
        <circle cx="16" cy="40" r="4" stroke="#F5A8C8"/>
        <circle cx="48" cy="40" r="4" stroke="#F5A8C8"/>
        <circle cx="32" cy="56" r="4" stroke="#F5A8C8"/>
        <line x1="32" y1="20" x2="16" y2="36" stroke="#F5A8C8"/>
        <line x1="32" y1="20" x2="48" y2="36" stroke="#F5A8C8"/>
        <line x1="16" y1="44" x2="32" y2="52" stroke="#F5A8C8"/>
        <line x1="48" y1="44" x2="32" y2="52" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-chat" style="width: 55px; height: 55px; top: 50%; right: 8%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M8 12c0-2 2-4 4-4h40c2 0 4 2 4 4v28c0 2-2 4-4 4h-28l-12 8v-8c-2 0-4-2-4-4V12z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-bed" style="width: 60px; height: 60px; top: 55%; left: 15%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <rect x="8" y="20" width="48" height="28" rx="2" stroke="#F5A8C8"/>
        <line x1="8" y1="36" x2="56" y2="36" stroke="#F5A8C8"/>
        <rect x="8" y="28" width="48" height="8" fill="none" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-cup" style="width: 50px; height: 50px; top: 70%; right: 12%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M16 24h32c2 0 4 2 4 4v16c0 2-2 4-4 4H16c-2 0-4-2-4-4V28c0-2 2-4 4-4z" stroke="#F5A8C8"/>
        <line x1="20" y1="28" x2="20" y2="20" stroke="#F5A8C8"/>
        <line x1="44" y1="28" x2="44" y2="20" stroke="#F5A8C8"/>
        <path d="M52 32c0 8-2 12-4 14" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-meditation" style="width: 55px; height: 55px; top: 35%; right: 25%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <circle cx="32" cy="16" r="6" stroke="#F5A8C8"/>
        <path d="M24 26c0-4 6-8 8-8s8 4 8 8" stroke="#F5A8C8"/>
        <path d="M20 32c-2 4-4 12-4 18 0 4 4 8 8 8h16c4 0 8-4 8-8 0-6-2-14-4-18" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-clipboard" style="width: 50px; height: 50px; top: 65%; left: 25%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <rect x="12" y="8" width="40" height="48" rx="2" stroke="#F5A8C8"/>
        <line x1="20" y1="20" x2="44" y2="20" stroke="#F5A8C8"/>
        <line x1="20" y1="30" x2="44" y2="30" stroke="#F5A8C8"/>
        <line x1="20" y1="40" x2="44" y2="40" stroke="#F5A8C8"/>
        <line x1="20" y1="50" x2="44" y2="50" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-star" style="width: 45px; height: 45px; top: 45%; left: 3%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 8l8 18h20l-16 12 6 18-18-13-18 13 6-18-16-12h20z" stroke="#F5A8C8"/>
    </svg>

    <!-- Medical Kit Icon -->
    <svg class="wellness-icon icon-medical" style="width: 55px; height: 55px; top: 20%; left: 45%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <rect x="12" y="16" width="40" height="40" rx="4" stroke="#F5A8C8"/>
        <line x1="32" y1="28" x2="32" y2="52" stroke="#F5A8C8"/>
        <line x1="20" y1="40" x2="44" y2="40" stroke="#F5A8C8"/>
    </svg>

    <!-- Sparkle Icons (small decorative stars) -->
    <svg class="wellness-icon icon-sparkle" style="width: 30px; height: 30px; top: 8%; right: 15%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 8l4 10h10l-8 6 3 10-9-7-9 7 3-10-8-6h10z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-sparkle" style="width: 25px; height: 25px; top: 60%; right: 5%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 8l4 10h10l-8 6 3 10-9-7-9 7 3-10-8-6h10z" stroke="#F5A8C8"/>
    </svg>

    <!-- Ring/Rings Icon -->
    <svg class="wellness-icon icon-rings" style="width: 50px; height: 50px; top: 72%; right: 30%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <circle cx="24" cy="32" r="12" stroke="#F5A8C8"/>
        <circle cx="40" cy="32" r="12" stroke="#F5A8C8"/>
    </svg>

    <!-- Small Dots -->
    <circle class="wellness-icon icon-dot" style="width: 12px; height: 12px; top: 18%; left: 60%; fill: #F5A8C8;" cx="6" cy="6" r="6"/>
    <circle class="wellness-icon icon-dot" style="width: 15px; height: 15px; top: 28%; left: 22%; fill: #F5A8C8;" cx="7.5" cy="7.5" r="7.5"/>
    <circle class="wellness-icon icon-dot" style="width: 10px; height: 10px; top: 48%; right: 35%; fill: #F5A8C8;" cx="5" cy="5" r="5"/>
    <circle class="wellness-icon icon-dot" style="width: 14px; height: 14px; top: 75%; left: 50%; fill: #F5A8C8;" cx="7" cy="7" r="7"/>
    <circle class="wellness-icon icon-dot" style="width: 11px; height: 11px; top: 30%; right: 5%; fill: #F5A8C8;" cx="5.5" cy="5.5" r="5.5"/>

    <!-- Mental Health Text Elements -->
    <div class="wellness-text text-mental-1" style="top: 25%; left: 20%;">Mental Health</div>
    <div class="wellness-text text-mental-2" style="top: 60%; right: 18%;">Mental Health</div>
    <div class="wellness-text text-mental-3" style="top: 75%; left: 8%;">Mental Health</div>

    <!-- Additional Sparkles -->
    <svg class="wellness-icon icon-sparkle" style="width: 28px; height: 28px; top: 32%; left: 35%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12l2 6h6l-5 3 2 6-5-4-5 4 2-6-5-3h6z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-sparkle" style="width: 24px; height: 24px; top: 68%; left: 70%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12l2 6h6l-5 3 2 6-5-4-5 4 2-6-5-3h6z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-sparkle" style="width: 26px; height: 26px; top: 42%; right: 50%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12l2 6h6l-5 3 2 6-5-4-5 4 2-6-5-3h6z" stroke="#F5A8C8"/>
    </svg>

    <!-- Pill/Capsule Icon -->
    <svg class="wellness-icon icon-pill" style="width: 48px; height: 48px; top: 52%; left: 40%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M16 28c0-4 4-8 8-8h16c4 0 8 4 8 8v8c0 4-4 8-8 8H24c-4 0-8-4-8-8v-8z" stroke="#F5A8C8"/>
        <line x1="32" y1="20" x2="32" y2="44" stroke="#F5A8C8"/>
    </svg>

    <!-- Water Drop Icon -->
    <svg class="wellness-icon icon-water" style="width: 42px; height: 42px; top: 15%; left: 70%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12c0 0-10 12-10 20 0 8 4 12 10 12s10-4 10-12c0-8-10-20-10-20z" stroke="#F5A8C8"/>
    </svg>

    <!-- Leaf Icon -->
    <svg class="wellness-icon icon-leaf" style="width: 45px; height: 45px; top: 38%; left: 58%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12c12 0 18 10 18 20 0 12-8 20-18 20s-18-8-18-20c0-10 6-20 18-20z" stroke="#F5A8C8"/>
        <line x1="32" y1="12" x2="32" y2="52" stroke="#F5A8C8"/>
    </svg>

    <!-- Clock Icon -->
    <svg class="wellness-icon icon-clock" style="width: 50px; height: 50px; top: 32%; left: 12%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <circle cx="32" cy="32" r="20" stroke="#F5A8C8"/>
        <line x1="32" y1="16" x2="32" y2="32" stroke="#F5A8C8"/>
        <line x1="32" y1="32" x2="44" y2="32" stroke="#F5A8C8"/>
    </svg>

    <!-- Smiley Face Icon -->
    <svg class="wellness-icon icon-smile" style="width: 52px; height: 52px; top: 20%; right: 35%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <circle cx="32" cy="32" r="20" stroke="#F5A8C8"/>
        <circle cx="26" cy="28" r="2" fill="#F5A8C8"/>
        <circle cx="38" cy="28" r="2" fill="#F5A8C8"/>
        <path d="M24 38c0 0 4 4 8 4s8-4 8-4" stroke="#F5A8C8"/>
    </svg>

    <!-- Flower Icon -->
    <svg class="wellness-icon icon-flower" style="width: 48px; height: 48px; top: 58%; right: 42%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <circle cx="32" cy="32" r="6" stroke="#F5A8C8"/>
        <circle cx="32" cy="12" r="5" stroke="#F5A8C8"/>
        <circle cx="46" cy="18" r="5" stroke="#F5A8C8"/>
        <circle cx="50" cy="32" r="5" stroke="#F5A8C8"/>
        <circle cx="46" cy="46" r="5" stroke="#F5A8C8"/>
        <circle cx="32" cy="52" r="5" stroke="#F5A8C8"/>
        <circle cx="18" cy="46" r="5" stroke="#F5A8C8"/>
        <circle cx="14" cy="32" r="5" stroke="#F5A8C8"/>
        <circle cx="18" cy="18" r="5" stroke="#F5A8C8"/>
    </svg>

    <!-- Raised Hand Icon (Wellness/Support) -->
    <svg class="wellness-icon icon-hand" style="width: 46px; height: 46px; top: 10%; left: 38%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M24 40v-16c0-2 2-4 4-4m0 24v-20c0-2 2-4 4-4m0 24v-20c0-2 2-4 4-4m0 24v-20c0-2 2-4 4-4m0 24v-16c0-2 2-4 4-4" stroke="#F5A8C8"/>
        <path d="M20 40c-2 0-4 2-4 4v12c0 2 2 4 4 4h24c2 0 4-2 4-4v-12c0-2-2-4-4-4h-24z" stroke="#F5A8C8"/>
    </svg>

    <!-- Sun Icon -->
    <svg class="wellness-icon icon-sun" style="width: 50px; height: 50px; top: 56%; left: 5%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <circle cx="32" cy="32" r="12" stroke="#F5A8C8"/>
        <line x1="32" y1="8" x2="32" y2="16" stroke="#F5A8C8"/>
        <line x1="48" y1="32" x2="56" y2="32" stroke="#F5A8C8"/>
        <line x1="32" y1="48" x2="32" y2="56" stroke="#F5A8C8"/>
        <line x1="16" y1="32" x2="8" y2="32" stroke="#F5A8C8"/>
        <line x1="44" y1="20" x2="50" y2="14" stroke="#F5A8C8"/>
        <line x1="44" y1="44" x2="50" y2="50" stroke="#F5A8C8"/>
        <line x1="20" y1="44" x2="14" y2="50" stroke="#F5A8C8"/>
        <line x1="20" y1="20" x2="14" y2="14" stroke="#F5A8C8"/>
    </svg>

    <!-- More Decorative Dots -->
    <circle class="wellness-icon icon-dot" style="width: 13px; height: 13px; top: 5%; right: 25%; fill: #F5A8C8;" cx="6.5" cy="6.5" r="6.5"/>
    <circle class="wellness-icon icon-dot" style="width: 9px; height: 9px; top: 42%; left: 88%; fill: #F5A8C8;" cx="4.5" cy="4.5" r="4.5"/>
    <circle class="wellness-icon icon-dot" style="width: 12px; height: 12px; top: 80%; right: 8%; fill: #F5A8C8;" cx="6" cy="6" r="6"/>
    <circle class="wellness-icon icon-dot" style="width: 10px; height: 10px; top: 38%; right: 65%; fill: #F5A8C8;" cx="5" cy="5" r="5"/>
    <circle class="wellness-icon icon-dot" style="width: 14px; height: 14px; top: 22%; left: 78%; fill: #F5A8C8;" cx="7" cy="7" r="7"/>

    <!-- More Sparkles -->
    <svg class="wellness-icon icon-sparkle" style="width: 22px; height: 22px; top: 12%; right: 48%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12l2 6h6l-5 3 2 6-5-4-5 4 2-6-5-3h6z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-sparkle" style="width: 20px; height: 20px; top: 58%; left: 80%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12l2 6h6l-5 3 2 6-5-4-5 4 2-6-5-3h6z" stroke="#F5A8C8"/>
    </svg>

    <svg class="wellness-icon icon-sparkle" style="width: 23px; height: 23px; top: 72%; left: 12%;" viewBox="0 0 64 64" fill="none" stroke-width="2">
        <path d="M32 12l2 6h6l-5 3 2 6-5-4-5 4 2-6-5-3h6z" stroke="#F5A8C8"/>
    </svg>

    <!-- Additional Mental Health Text -->
    <div class="wellness-text text-mental-1" style="top: 82%; right: 28%;">Mental Health</div>
    <div class="wellness-text text-mental-2" style="top: 12%; left: 55%;">Mental Health</div>
    """, unsafe_allow_html=True)
