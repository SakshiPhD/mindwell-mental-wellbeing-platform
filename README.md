# 🧠 MindWell - AI Mental Health Companion

MindWell is an empathetic, AI-powered mental health support application built with **Streamlit**, **LangChain**, and **PostgreSQL (Neon)**. It features a sophisticated Multi-Agent architecture with conditional memory/RAG, intelligent crisis detection, and advanced safety protocols.

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

## 💻 Setup & Running

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
# Update .streamlit/secrets.toml with Neon credentials
```

### Running the App

```bash
streamlit run app.py
```

App runs on `http://localhost:8501` (or next available port)

### Database Setup

1. Create Neon project at https://console.neon.tech
2. Add credentials to `.streamlit/secrets.toml`:
```toml
[database]
host = "your-neon-host.neon.tech"
user = "your_user"
password = "your_password"
database = "neondb"
```

3. Database tables initialize automatically on first run

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

## 📋 Key Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit entry point, page routing |
| `pages.py` | UI components, intent detection, RAG/memory logic |
| `engine.py` | Multi-agent orchestration, routing decisions |
| `database.py` | PostgreSQL/Neon operations, session management |
| `rag.py` | Vector search, chunk retrieval, embedding |
| `llm_provider.py` | LLM calls, model management |
| `config.py` | Configuration, constants |
| `styles.py` | CSS styling, UI themes |

---

## 📚 Documentation

For detailed documentation on specific components:
- **Intent Detection**: See `pages.py` lines 232-327
- **Dynamic RAG**: See `pages.py` lines 254-270
- **Safety Protocol**: See `engine.py` lines 286-292
- **Grounding Detection**: See `pages.py` lines 53-119
- **Crisis Response**: See `pages.py` lines 2645-2664

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

**Last Updated**: April 2026
**Version**: 2.0 (Safety & RAG Improvements)
