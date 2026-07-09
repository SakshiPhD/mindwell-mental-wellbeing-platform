# 🚀 MindWell - Setup and Run Instructions

Complete step-by-step guide to set up and run the MindWell Mental Health AI Platform.

---

## 📋 Prerequisites

Before you begin, ensure you have:

- **Python 3.9+** installed ([Download here](https://www.python.org/downloads/))
- **Git** installed ([Download here](https://git-scm.com/))
- **Neon PostgreSQL account** (free tier available at https://console.neon.tech)
- **OpenAI API key** (or Ollama/Llama 3.1 if using local LLM)
- **Streamlit** will be installed automatically via `requirements.txt`

### Verify Installation

```bash
python --version  # Should be 3.9+
git --version     # Should be 2.0+
```

---

## 🛠️ Step 1: Clone the Repository

```bash
# Clone the project
git clone https://github.com/yourusername/mindwell-mental-wellbeing-platform.git

# Navigate to project directory
cd mindwell-mental-wellbeing-platform
```

---

## 🔧 Step 2: Create Virtual Environment

### **Windows**

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate
```

**Expected output:** `(.venv)` appears in your terminal

### **macOS / Linux**

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate
```

**Expected output:** `(.venv)` appears in your terminal

---

## 📦 Step 3: Install Dependencies

```bash
# Upgrade pip (recommended)
pip install --upgrade pip

# Install all required packages
pip install -r requirements.txt
```

**This installs:**
- Streamlit (web framework)
- LangChain (LLM orchestration)
- Psycopg2 (PostgreSQL driver)
- NumPy, Pandas (data processing)
- FAISS (vector search)
- And other dependencies

---

## 🔐 Step 4: Configure Environment Variables

### **Create .env file from template**

```bash
# Copy the example file
cp .env.example .env
```

### **Edit .env file**

Open `.env` in your text editor and fill in your credentials:

```bash
# ==================== DATABASE ====================
DB_HOST=your-project.neon.tech
DB_PORT=5432
DB_NAME=neondb
DB_USER=your_database_user
DB_PASSWORD=your_secure_password
DB_SSLMODE=require

# ==================== LLM PROVIDER ====================
LLM_PROVIDER=openai
LLM_API_KEY=your_openai_api_key_here
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.7

# ==================== STREAMLIT ====================
STREAMLIT_SERVER_PORT=8501
STREAMLIT_LOGGER_LEVEL=info

# ==================== APPLICATION ====================
DEBUG_MODE=false
SESSION_TIMEOUT_MINUTES=15
```

### **How to get credentials:**

#### **Database Credentials (Neon PostgreSQL)**
1. Go to https://console.neon.tech
2. Sign up or log in
3. Create a new project
4. Copy the connection details:
   - `DB_HOST` from "Pooler connection string"
   - `DB_USER` and `DB_PASSWORD` from "Connection details"
   - `DB_NAME` (usually `neondb`)

#### **LLM API Key**
- **OpenAI**: Get from https://platform.openai.com/api-keys
- **Ollama**: No key needed; set `LLM_PROVIDER=ollama` and ensure Ollama is running locally

---

## 🗄️ Step 5: Streamlit Secrets Configuration (Optional)

For production or advanced setup, you can also configure `.streamlit/secrets.toml`:

```bash
# Copy secrets template
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

```toml
[postgres]
host = "your-project.neon.tech"
port = 5432
database = "neondb"
user = "your_database_user"
password = "your_secure_password"
sslmode = "require"

[llm]
provider = "openai"
api_key = "your_api_key_here"
model = "gpt-4"
temperature = 0.7

[app]
debug_mode = false
session_timeout_minutes = 15
```

---

## 🚀 Step 6: Run the Application

### **Start Streamlit Server**

```bash
streamlit run app.py
```

### **Expected Output**

```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

### **Open in Browser**

- Click the **Local URL** link or manually open `http://localhost:8501`
- You should see the MindWell login page

---

## ✅ Step 7: Verify Setup

### **Database Connection**

- Look for **"✅ Connected to Neon PostgreSQL"** in the sidebar
- If you see ❌, check your `.env` credentials

### **LLM Connection**

- Send a test message: "Hi, how are you?"
- The bot should respond within a few seconds
- If no response, check your LLM API key

### **First Login**

1. **Sign Up** with:
   - Email: `test@example.com`
   - Full Name: `Test User`
   - Password: `test123`
   
2. **Create Profile** with:
   - Age
   - Gender
   - Location
   - Trusted Adult Name (for crisis support)

3. **Start Chatting** - Send a test message!

---

## 🐛 Troubleshooting

### **Issue: "ModuleNotFoundError: No module named 'streamlit'"**

**Solution:**
```bash
# Make sure virtual environment is activated
# Then reinstall dependencies
pip install -r requirements.txt
```

### **Issue: "Can't connect to database"**

**Check:**
- ✅ `.env` file exists with correct credentials
- ✅ Neon project is active (not paused)
- ✅ Your IP is not blocked by firewall
- ✅ Database credentials are correct

**Test connection:**
```bash
python -c "import psycopg2; print('Connection test')"
```

### **Issue: "LLM API key invalid"**

**Solution:**
- Verify API key is correct at https://platform.openai.com/api-keys
- Check `LLM_PROVIDER` matches your service (openai, ollama, etc.)
- Ensure you have API credits

### **Issue: Port 8501 already in use**

**Solution:**
```bash
# Run on different port
streamlit run app.py --server.port 8502
```

### **Issue: Streamlit page not loading**

**Solution:**
```bash
# Clear Streamlit cache
rm -rf ~/.streamlit/cache

# Restart the app
streamlit run app.py
```

### **Issue: OTP not sending in signup**

**Current Status:** Demo mode - OTP prints to terminal instead of email
- Check terminal for OTP code
- Or set `DEMO_MODE = False` in `config.py` if using real email service

---

## 📊 First-Time User Walkthrough

### **1. Signup & Onboarding**
- Create account with email and password
- Complete profile setup
- Add trusted adult contact info

### **2. Chat Interface**
- Type your message in the input box
- Click "Send" or press Enter
- Bot responds in real-time

### **3. Conversation Features**
- 💬 **General Chat**: Casual conversation
- 📝 **Event Sharing**: Tell about your day
- 😟 **Emotional Support**: Share feelings and concerns
- 🆘 **Crisis Support**: Immediate help if needed
- 💡 **Coping Techniques**: Get mental health advice

### **4. Session History**
- All messages are saved automatically
- Reload the page to see conversation history
- Sessions timeout after 15 minutes of inactivity

---

## 🔒 Security Notes

### **Keep Safe**
- ✅ Never commit `.env` or `.streamlit/secrets.toml`
- ✅ Keep your API keys and database passwords private
- ✅ Don't share your `.env` file

### **Best Practices**
- Use strong database passwords
- Rotate API keys regularly
- Enable 2FA on your Neon account
- Monitor API usage on OpenAI dashboard

---

## 📱 Accessing from Other Devices

### **Local Network Access**

The "Network URL" shown in terminal allows access from other devices:

```
Network URL: http://192.168.x.x:8501
```

**From another device:**
- Open the Network URL in a browser
- Works on phones, tablets, other computers on same network

### **Remote Access** (Not recommended for local development)

To make app accessible online, you would need to:
- Deploy to cloud (Streamlit Cloud, Heroku, AWS, etc.)
- Set up proper authentication
- Use HTTPS
- Configure CORS properly

---

## 🛑 Stopping the Application

**Press `Ctrl + C`** in your terminal to stop the Streamlit server.

---

## 🔄 Restarting After Closing

```bash
# Navigate to project directory
cd mindwell-mental-wellbeing-platform

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate

# Run the app
streamlit run app.py
```

---

## 📚 Next Steps

### **To Customize:**
1. **UI Styling**: Edit `styles.py`
2. **Configuration**: Edit `config.py`
3. **Database Schema**: Edit `database.py`
4. **LLM Behavior**: Edit `engine.py`

### **To Deploy:**
1. Set up Streamlit Cloud account
2. Connect GitHub repository
3. Configure secrets in Streamlit Cloud
4. Deploy with one click

### **To Contribute:**
- See `README.md` for architecture details
- Follow coding guidelines in `CONTRIBUTING.md`
- Submit pull requests with documentation

---

## ❓ Getting Help

### **Documentation**
- Read `README.md` for system architecture
- Check code comments for implementation details
- Review `engine.py` for multi-agent logic

### **Common Issues**
- **Database**: Check Neon PostgreSQL logs at https://console.neon.tech
- **LLM**: Test API key at https://platform.openai.com/playground
- **Streamlit**: Run `streamlit config show` to check configuration

### **Debug Mode**

Enable debug logging in `.env`:

```bash
DEBUG_MODE=true
STREAMLIT_LOGGER_LEVEL=debug
```

Then restart the app to see detailed logs.

---

**Last Updated:** May 2026  
**Version:** 1.0  
**Status:** Ready for Production Use ✨
