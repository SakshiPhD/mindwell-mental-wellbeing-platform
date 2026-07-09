# 🧠 MindWell — AI Mental Wellbeing Platform

**MindWell** is an empathetic, AI-powered mental health support application built to raise
awareness about mental wellbeing and provide stress-management and basic counselling-style
interactions. It combines a multi-agent architecture (Safety, Memory, Orchestrator, Coach),
conditional memory + Retrieval-Augmented Generation (RAG), crisis detection, and safety
protocols.

Built with **Streamlit**, **Python**, **LangChain**, an **LLM provider (OpenAI or Ollama/Llama 3.1)**,
**FAISS** for vector search, and **PostgreSQL (Neon)** for storage.

> ⚠️ **Important:** MindWell is an educational / prototype project. It is **not a substitute for
> professional mental health care**. In a genuine crisis, contact local emergency services or a
> crisis hotline.

---

## 📂 Repository Structure

```
.
├── source_code/          # The application (run everything from here)
│   ├── app.py            # Streamlit entry point
│   ├── pages.py          # UI, intent detection, conditional RAG/memory
│   ├── engine.py         # Multi-agent orchestration (Safety/Memory/Orchestrator/Coach)
│   ├── rag.py            # Vector embeddings + semantic search
│   ├── knowledge_base.py # Knowledge-base handling
│   ├── ingest_documents.py # Builds the RAG index from the source PDFs
│   ├── llm_provider.py   # LLM calls / model management
│   ├── database.py       # PostgreSQL (Neon) operations
│   ├── config.py         # Configuration and constants
│   ├── styles.py         # CSS styling and themes
│   ├── requirements.txt  # Python dependencies
│   ├── .env.example      # Environment-variable template
│   └── README.md         # Full architecture & feature documentation
├── documents/            # Source PDFs used to build the RAG knowledge base
├── documentation/        # Architecture diagram, DB schema, setup guide
│   ├── Architecture_Diagram.png.png
│   ├── Database_Schema.sql
│   └── Setup_and_Run_Instructions.md
├── migrations/           # SQL migrations
├── .streamlit/           # Streamlit config + secrets template
├── LICENSE
└── README.md             # (this file)
```

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.9+**
- A **PostgreSQL** database — a free [Neon](https://console.neon.tech) project works well
- An **LLM provider**: an **OpenAI API key**, or **[Ollama](https://ollama.com)** running locally with Llama 3.1

### 1. Clone and enter the project
```bash
git clone https://github.com/SakshiPhD/mindwell-mental-wellbeing-platform.git
cd mindwell-mental-wellbeing-platform/source_code
```

### 2. Create and activate a virtual environment
```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
cp .env.example .env
# then edit .env and fill in your database + LLM credentials
```

Key variables (see `source_code/.env.example` for the full list):

| Variable | Purpose |
|----------|---------|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL / Neon connection |
| `LLM_PROVIDER` | `openai` or `ollama` |
| `LLM_API_KEY`, `LLM_MODEL` | LLM credentials and model |

> Never commit your `.env` or `.streamlit/secrets.toml` — both are git-ignored.

### 5. (Optional) Build the RAG knowledge base
The `documents/` folder ships with the source PDFs. To (re)build the vector index:
```bash
python ingest_documents.py
```

### 6. Run the app
```bash
streamlit run app.py
```
Open **http://localhost:8501** in your browser.

---

## 📖 Documentation

- **Full architecture, features, database schema, and testing scenarios:**
  [`source_code/README.md`](source_code/README.md)
- **Detailed step-by-step setup & troubleshooting:**
  [`documentation/Setup_and_Run_Instructions.md`](documentation/Setup_and_Run_Instructions.md)
- **Database schema:** [`documentation/Database_Schema.sql`](documentation/Database_Schema.sql)

---

## ✨ Key Features
- Smart intent detection (casual chat vs. event sharing vs. emotional support vs. crisis)
- Conditional memory & dynamic RAG retrieval (only when the query needs it)
- Multi-agent design: Safety, Memory, Orchestrator, and Coach agents
- Crisis detection with trusted-adult escalation and safety protocols
- Session persistence with full chat history in PostgreSQL

---

## 📝 License
See [LICENSE](LICENSE). Provided as-is for educational and mental-health-awareness purposes.
```