# 🧠 MindWell - AI Mental Health Companion

**MindWell** is an empathetic, AI-powered mental health support application designed to raise awareness about mental wellbeing. It provides intelligent emotional support through a sophisticated Multi-Agent architecture with conditional memory/RAG, intelligent crisis detection, and advanced safety protocols.

Built with **Streamlit**, **Python**, **LangChain**, **Ollama/Llama 3.1**, and **PostgreSQL (Neon)**, MindWell serves as an educational platform for understanding mental health support systems and AI-driven coaching.

## 🚀 Key Features

- **Smart Intent Detection**: Distinguishes between casual chat, event sharing, emotional responses, coping requests, and crisis situations
- **Conditional Memory & RAG**: Only uses memory for emotional patterns and RAG for knowledge-heavy queries
- **Dynamic RAG Retrieval**: Top-K chunks (1-5) determined by message length and intent complexity
- **Advanced Safety Protocols**: Crisis intervention with trusted adult escalation, not generic hotlines
- **Intelligent Grounding Detection**: Analyzes if bot responses actually use retrieved chunks
- **Session Persistence**: Seamless session continuation with full chat history
- **Multi-Agent Intelligence**: Specialized agents for Safety, Memory, Orchestration, and Coaching
- **Neon Database Integration**: Secure PostgreSQL storage with comprehensive tracking

---

## 🛠️ Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Frontend Framework** | Streamlit | Latest |
| **Language** | Python | 3.9+ |
| **LLM Provider** | Ollama/Llama 3.1 | Latest |
| **Vector Database** | FAISS/ChromaDB | Latest |
| **Database** | PostgreSQL (Neon) | 14+ |
| **Libraries** | LangChain, NumPy, Pandas, Psycopg2 | Latest |
| **Authentication** | Streamlit Session Management | Built-in |

---

## 🏗️ System Architecture

### 1. Core Agents (`engine.py`)

Four specialized agents work together for intelligent responses:

| Agent | Role | When Active | Output |
|-------|------|------------|--------|
| **🛡️ Safety** | Risk/harm detection | Every message | Risk level, safety action |
| **📝 Memory** | Emotional tracking, facts | Only when needed | User facts, mood patterns |
| **🎯 Orchestrator** | Intent routing, context | Always | Intent classification |
| **💙 Coach** | Crisis support, grounding | High/Extreme risk | Immediate intervention |

### 2. Intent Detection System

**Smart Classification** (`pages.py` / `engine.py`):

```
Message Analysis
├─ Contains emotion words? (sad, anxious, scared, etc.)
│  ├─ YES + Event → emotional_response (use memory, no RAG)
│  └─ NO + Event → event_sharing (no memory, no RAG)
├─ Coping/technique request? → coping_request (use RAG)
├─ Mental health info? → mental_health_info (use RAG)
├─ Crisis language? → crisis (emergency protocol)
└─ DEFAULT → general_chat (no memory, no RAG)
```

**Key Distinction**: 
- ✅ `event_sharing`: "I went to a concert today" → No memory/RAG
- ✅ `emotional_response`: "I'm anxious about my presentation" → Memory only
- ✅ `coping_request`: "How do I handle anxiety?" → RAG only

### 3. Conditional Memory System

Memory is **only fetched** when:
```python
memory_needed in ["light", "full"]  # Not "false"
```

**Use Cases**:
- ✅ Emotional responses: Track patterns over time
- ✅ Crisis situations: Reference past coping attempts
- ❌ Casual greetings: No memory needed
- ❌ Event sharing: No emotional context needed

### 4. Dynamic RAG System

**Top-K Selection** (`_get_rag_top_k()`):
```
Crisis intent           → top_k = 5 chunks (max safety context)
Message > 200 chars     → top_k = 4 chunks (complex query)
Message > 100 chars     → top_k = 3 chunks (detailed)
Message > 50 chars      → top_k = 2 chunks (normal)
Message ≤ 50 chars      → top_k = 1 chunk (quick answer)
```

**RAG Retrieval Only For**:
- ✅ `coping_request`: Techniques and strategies
- ✅ `mental_health_info`: Educational content
- ✅ `crisis`: Emergency resources
- ❌ Everything else

### 5. Advanced Safety & Crisis Protocol

#### Crisis Detection
Triggers when message contains:
- Suicidal ideation: "I want to die", "no point in living"
- Self-harm: "I want to hurt myself"
- Hopelessness: "I can't keep going"

#### Crisis Response
```python
IF risk_level == "extreme":
  1. Check for harmful validation language (INTERRUPT if found)
  2. Fetch trusted_adult_name from user profile
  3. Redirect immediately to trusted adult contact
  4. DO NOT provide coping tips or memory comparisons
  5. Keep response SHORT: 1-2 sentences max
```

**Example Response**:
```
User: "I'm thinking about ending my life tonight"

Bot: "Please reach out to your mom RIGHT NOW and tell her 
you need immediate support. She cares about you."
```

### 6. Intelligent Grounding Detection

**`check_response_grounded()`** analyzes if response uses retrieved chunks:

```python
4 Detection Methods:
├─ Exact phrase matching (0.8 score)
├─ Citation language detection (0.6 score)
├─ Keyword overlap (Jaccard similarity, 0.7 score)
└─ Response detail length (0.4 score)

Final Score = AVERAGE of detected signals (0.0-1.0)
```

**Flag Logic**:
```python
grounded_flag = (
    rag_used AND 
    retrieval_score >= 0.65 AND 
    check_response_grounded(response) >= 0.5
)

rag_benefit_flag = (
    grounded_flag AND 
    retrieval_score >= 0.70 AND 
    len(response) > 100
)
```

---

## 📊 Database Schema

### Core Tables

#### `chat_messages`
```sql
Tracks every user-bot exchange

Fields:
├─ serial_no (INT PRIMARY KEY)      -- Auto-incrementing, no gaps
├─ user_id, session_id              -- Session tracking
├─ user_message, assistant_response -- Conversation content
├─ user_msg_timestamp, bot_msg_timestamp
├─ latency_seconds                  -- Response time
├─ risk_level                       -- low/medium/high/extreme
├─ safety_action                    -- normal/supportive/immediate
├─ intent_label                     -- Detected intent type
├─ response_mode                    -- normal_chat/supportive/crisis
├─ memory_used (BOOL)               -- Was memory fetched?
├─ memory_type                      -- Type of memory (or "-")
├─ rag_used (BOOL)                  -- Was RAG used?
├─ doc_id (INT[])                   -- Retrieved chunk IDs
├─ rag_source (TEXT)                -- Document sources (or "-")
├─ retrieved_count (INT)            -- Number of chunks
├─ retrieval_score (FLOAT)          -- AVG similarity score
├─ grounded_flag (BOOL)             -- Response uses chunks?
├─ rag_benefit_flag (BOOL)          -- Did RAG help quality?
└─ ... (legacy fields)
```

#### `chat_analysis`
```sql
Session-level analysis and summaries

Fields:
├─ serial_no (INT PRIMARY KEY)      -- Sequential ID
├─ user_id, session_id              -- Session tracking
├─ summary_text                     -- Auto-generated summary
├─ detected_tone                    -- User's emotional tone
├─ user_facts_json                  -- Extracted facts
├─ last_risk_level                  -- Session's max risk
├─ escalation_flag                  -- Did it escalate?
├─ dominant_emotion                 -- Primary emotion
├─ repeated_stressors               -- Recurring issues
└─ risk_trend                       -- Rising/stable/improving
```

### Clean Data Standards

**Blank Fields Use "-" Sentinel** (not NULL):
```python
rag_source = "-"          # No RAG used
memory_type = "-"         # No memory type
```

---

## 🔄 Session Persistence

### How Sessions Work

1. **Session Creation**: First message starts new session
2. **Session Resume**: Returning users see last active session
3. **Message Loading**: Previous messages loaded from `chat_messages`
4. **Continuity Detection**: Bot recognizes session references
5. **Session Timeout**: Inactive sessions finalized after 15 minutes

### Example Flow
```
User closes app after Message 5
→ Session state saved to DB
↓
User returns 2 hours later
→ Old session loaded automatically
→ Messages 1-5 displayed
→ User sends Message 6 (continues same session)
→ All messages 1-6 visible in chat window
```

---

## 🧪 Testing & Verification

### Test Scenarios

**Test 1: Casual Chat (No Memory/RAG)**
```
User: "Hi, how are you today?"
Expected: intent_label=general_chat, memory_used=False, rag_used=False
```

**Test 2: Event Sharing (No Memory/RAG)**
```
User: "I went to a concert yesterday"
Expected: intent_label=event_sharing, memory_used=False, rag_used=False
```

**Test 3: Emotional Response (Memory Only)**
```
User: "I'm anxious about my presentation and can't sleep"
Expected: intent_label=emotional_response, memory_used=True, rag_used=False
```

**Test 4: Coping Request (RAG Only)**
```
User: "What are breathing techniques for anxiety?"
Expected: intent_label=coping_request, memory_used=False, rag_used=True
```

**Test 5: Crisis Detection (Maximum Safety)**
```
User: "I want to end my life tonight"
Expected: risk_level=extreme, safety_action=immediate
Response: Redirects to trusted adult (not generic hotline)
```

### Verification Checklist

- [ ] Database contains "-" for blank fields (not NULL)
- [ ] retrieved_count = 1-5 based on message length
- [ ] retrieval_score = AVG of chunk similarities
- [ ] grounded_flag = True only when response uses chunks
- [ ] rag_benefit_flag = True only for high-quality, grounded, detailed responses
- [ ] Crisis responses immediately redirect to trusted adult
- [ ] Session history loads on reopening old sessions
- [ ] Memory disabled when risk_level = extreme

---

## 📁 Folder Structure

```
mindwell-mental-wellbeing-platform/
├── app.py                      # Main Streamlit application entry point
├── pages.py                    # UI components and page logic
├── engine.py                   # Multi-agent orchestration and routing
├── database.py                 # PostgreSQL/Neon operations
├── rag.py                      # Vector search and chunk retrieval
├── llm_provider.py             # LLM calls and model management
├── config.py                   # Configuration and constants
├── styles.py                   # CSS styling and themes
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
└── README.md                   # This file
```

### Key Components
- **app.py**: Streamlit page router and session management
- **pages.py**: UI rendering, intent detection, and conditional RAG/memory logic
- **engine.py**: Multi-agent system (Safety, Memory, Orchestrator, Coach agents)
- **rag.py**: Vector embeddings and semantic search implementation
- **database.py**: PostgreSQL connection pooling and query management

---

## 💻 Setup & Running

### Installation Steps

**1. Clone the repository:**
```bash
git clone <repository-url>
cd mindwell-mental-wellbeing-platform
```

**2. Create virtual environment:**
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies:**
```bash
pip install -r requirements.txt
```

**4. Configure environment variables:**
```bash
# Copy the example file
cp .env.example .env

# Edit .env with your actual credentials
# (Database host, user, password, LLM API keys, etc.)
```

### Run Command

Start the application:
```bash
streamlit run app.py
```

The app will be available at **`http://localhost:8501`** (or the next available port)

---

## 🔧 Environment Variables

The following variables must be set in your `.env` file:

### Database Configuration
```bash
DB_HOST=<your-neon-host>.neon.tech          # Neon PostgreSQL host
DB_PORT=5432                                 # PostgreSQL port
DB_NAME=mindwell_db                          # Database name
DB_USER=<your-database-user>                 # Database user
DB_PASSWORD=<your-secure-password>           # Database password
```

### LLM Provider Configuration
```bash
LLM_PROVIDER=openai                          # LLM provider (openai, ollama, etc.)
LLM_API_KEY=<your-api-key>                   # API key for LLM service
LLM_MODEL=gpt-4                              # Model to use
LLM_TEMPERATURE=0.7                          # Response creativity (0.0-1.0)
```

### Streamlit Configuration
```bash
STREAMLIT_SERVER_PORT=8501                   # Port to run Streamlit on
STREAMLIT_LOGGER_LEVEL=info                  # Logging level
```

### Application Settings
```bash
DEBUG_MODE=false                             # Enable debug logging
SESSION_TIMEOUT_MINUTES=15                   # Inactive session timeout
```

> ⚠️ **Security**: Never commit the `.env` file. Use `.env.example` as a template.

---

## 🗄️ Database Setup

### Neon PostgreSQL Setup

**1. Create Neon project:**
- Visit https://console.neon.tech
- Sign up or log in
- Create a new project and database
- Copy the connection string

**2. Add credentials to `.env`:**
```bash
DB_HOST=<your-project>.neon.tech
DB_USER=<username>
DB_PASSWORD=<password>
DB_NAME=neondb
```

**3. Initialize database tables:**
The application automatically creates required tables on first run:
- `chat_messages` - Stores all user-bot exchanges with metadata
- `chat_analysis` - Session-level analysis and summaries
- `rag_documents` - Vector embeddings for retrieval

**4. Verify connection:**
```bash
# The app will show a green "✅ Connected" indicator on the sidebar
# If connection fails, check your .env file and Neon credentials
```

### Table Schema

**chat_messages** table tracks:
- Message content and timestamps
- Risk levels and safety actions
- Intent classification
- Memory and RAG usage
- Grounding and quality metrics

**chat_analysis** table tracks:
- Session summaries
- Emotional tone detection
- Extracted user facts
- Risk escalation flags

---

## 🛠️ Recent Updates (Phase 1: Critical Safety)

### Safety Improvements
- ✅ **Crisis Protocol**: Added explicit suicidal ideation handling in agent prompt
- ✅ **Memory Disabling**: Memory skipped when risk_level=extreme (not distracted by past)
- ✅ **Trusted Adult Injection**: Personalizes crisis response with user's trusted adult name
- ✅ **Response Interruption**: Detects and BLOCKS harmful validation language

### RAG & Grounding Improvements
- ✅ **Intelligent Grounding**: Analyzes if response actually uses chunks (not just "if RAG used")
- ✅ **Advanced Detection**: Checks for exact phrases, citations, keyword overlap, detail length
- ✅ **Conditional RAG**: Dynamic top_k based on intent and message complexity
- ✅ **Clean Flags**: grounded_flag and rag_benefit_flag based on quality metrics

### Database Improvements
- ✅ **Deadlock Retry**: Automatic retry with exponential backoff (3 attempts)
- ✅ **Session Persistence**: Messages persist across session reopens
- ✅ **Clean Data**: All blank fields use "-" sentinel instead of NULL

---

## 📚 Documentation

For detailed documentation on specific components:
- **Intent Detection**: See `pages.py` lines 232-327
- **Dynamic RAG**: See `pages.py` lines 254-270
- **Safety Protocol**: See `engine.py` lines 286-292
- **Grounding Detection**: See `pages.py` lines 53-119
- **Crisis Response**: See `pages.py` lines 2645-2664

---

---

## ⚠️ Known Limitations

This is a **prototype/educational version** with the following current limitations:

### Feature Limitations
- **Single User Mode**: Currently supports one user per session; multi-user authentication not implemented
- **Offline LLM**: Uses Ollama locally; requires model download (Llama 3.1, ~7GB)
- **Limited Context Window**: Memory stores only last 20 sessions; older data archived
- **RAG Scope**: Knowledge base limited to uploaded documents; no real-time web search
- **Conversation Limit**: Sessions timeout after 15 minutes of inactivity

### Safety & Functionality
- **Not a Replacement**: Should NOT be used as a substitute for professional mental health care
- **Crisis Protocol**: Redirects to trusted adult (requires manual setup); no SMS/call integration
- **Language**: Currently English-only; no multi-language support
- **Accessibility**: Limited screen reader support; UI not fully optimized for mobile

### Technical Constraints
- **Vector DB**: Uses in-memory FAISS; no persistent vector store between sessions
- **Scaling**: Single-instance only; not designed for production multi-user deployment
- **Monitoring**: No built-in monitoring, alerting, or usage analytics
- **Backup**: Manual database backups required; no automated backup system

### Deployment
- **Local Only**: Designed for local development; cloud deployment requires configuration
- **No API**: Currently web UI only; no REST API for integration

---

## 🤝 Contributing

When adding features, keep in mind:
- **Safety First**: Any new risk detection should trigger immediate intervention
- **Intent Aware**: Check if feature applies to specific intents
- **Memory Conscious**: Don't use memory when not needed (wastes tokens)
- **RAG Smart**: Only retrieve chunks when knowledge is required
- **Clean Data**: Use "-" for blank text fields in DB

---

## 📝 License

MindWell is provided as-is for educational and mental health support purposes.

---

## ⚠️ Important Note

This application is designed to provide supportive chat for mental health awareness. It is **NOT a substitute for professional mental health care**. In genuine crisis situations, users should contact local emergency services or crisis hotlines.

---

**Last Updated**: May 2026
**Version**: 2.1 (Complete Documentation & Setup Guide)
