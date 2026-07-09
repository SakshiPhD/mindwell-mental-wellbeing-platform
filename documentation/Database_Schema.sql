-- ============================================================
-- MindWell Mental Health Platform - Database Schema
-- PostgreSQL (Neon) Database Schema
-- ============================================================

-- ============================================================
-- TABLE: users
-- Purpose: Store user account and profile information
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    dob DATE,
    gender VARCHAR(50),
    role VARCHAR(100),
    country VARCHAR(100),
    state VARCHAR(100),
    city VARCHAR(100),
    pincode VARCHAR(20),
    mobile_number VARCHAR(20),
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE: sessions
-- Purpose: Track user sessions for continuity
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    session_metadata JSONB
);

-- ============================================================
-- TABLE: chat_messages
-- Purpose: Store all user-bot exchanges with metadata
-- Description: Core table tracking every conversation turn
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    serial_no SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,

    -- Message Content
    user_message TEXT,
    assistant_response TEXT,

    -- Timestamps
    user_msg_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    bot_msg_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Performance Metrics
    latency_seconds FLOAT,

    -- Safety & Intent Classification
    risk_level VARCHAR(20) DEFAULT 'low',  -- low, medium, high, extreme
    safety_action VARCHAR(100),  -- normal, supportive, immediate
    intent_label VARCHAR(100),   -- general_chat, event_sharing, emotional_response, coping_request, crisis, mental_health_info
    response_mode VARCHAR(100),  -- normal_chat, supportive, crisis

    -- Memory Usage
    memory_used BOOLEAN DEFAULT FALSE,
    memory_type VARCHAR(100),    -- light, full, or "-"

    -- RAG (Retrieval-Augmented Generation) Usage
    rag_used BOOLEAN DEFAULT FALSE,
    doc_id INT[],                -- Array of retrieved document IDs
    rag_source TEXT,             -- Source documents or "-"
    retrieved_count INT,         -- Number of chunks retrieved (1-5)
    retrieval_score FLOAT,       -- Average similarity score (0.0-1.0)

    -- Grounding & Quality Metrics
    grounded_flag BOOLEAN DEFAULT FALSE,      -- Response uses retrieved chunks?
    rag_benefit_flag BOOLEAN DEFAULT FALSE,   -- Did RAG improve response quality?

    -- Legacy/Additional Fields
    visible_serial_no INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_risk_level ON chat_messages(risk_level);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(user_msg_timestamp);

-- ============================================================
-- TABLE: chat_analysis
-- Purpose: Session-level analysis and summaries
-- Description: Stores aggregated insights from conversations
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_analysis (
    serial_no SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    session_id VARCHAR(255) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,

    -- Session Analysis
    summary_text TEXT,           -- Auto-generated session summary
    detected_tone VARCHAR(100),  -- User's emotional tone
    user_facts_json JSONB,       -- Extracted facts and context

    -- Risk Assessment
    last_risk_level VARCHAR(20) DEFAULT 'low',
    risk_trend VARCHAR(50),      -- rising, stable, improving
    escalation_flag BOOLEAN DEFAULT FALSE,

    -- Emotional Patterns
    dominant_emotion VARCHAR(100),
    repeated_stressors TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_chat_analysis_user_id ON chat_analysis(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_analysis_session_id ON chat_analysis(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_analysis_risk_level ON chat_analysis(last_risk_level);

-- ============================================================
-- TABLE: rag_documents
-- Purpose: Store knowledge base documents for RAG
-- Description: Vector embeddings and document chunks
-- ============================================================
CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    content TEXT,
    source VARCHAR(255),        -- Document source (URL, file, etc.)
    chunk_index INT,            -- Chunk number within document
    embedding_vector FLOAT8[],  -- Vector embedding (1536-dim for OpenAI)
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON rag_documents(source);

-- ============================================================
-- TABLE: trusted_adults
-- Purpose: Store trusted adult contacts for crisis intervention
-- Description: User's emergency contacts for escalation
-- ============================================================
CREATE TABLE IF NOT EXISTS trusted_adults (
    contact_id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    relationship VARCHAR(100),  -- Parent, Guardian, Counselor, Friend, etc.
    phone_number VARCHAR(20),
    email VARCHAR(255),
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- TABLE: audit_log
-- Purpose: Track system activities for monitoring
-- Description: Security and activity audit trail
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_log (
    log_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id) ON DELETE SET NULL,
    action VARCHAR(255),        -- login, signup, message_sent, crisis_escalated, etc.
    details JSONB,
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for auditing
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(created_at);

-- ============================================================
-- TABLE: feedback
-- Purpose: Store user feedback for improvement
-- Description: Feedback on responses and platform
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id) ON DELETE SET NULL,
    message_id INT REFERENCES chat_messages(serial_no) ON DELETE CASCADE,
    rating INT CHECK (rating >= 1 AND rating <= 5),  -- 1-5 star rating
    comment TEXT,
    category VARCHAR(100),      -- helpful, not_helpful, inappropriate, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- VIEWS - Useful Queries
-- ============================================================

-- View: Recent conversations
CREATE OR REPLACE VIEW recent_conversations AS
SELECT
    u.user_id,
    u.username,
    u.full_name,
    cm.session_id,
    COUNT(*) as message_count,
    MAX(cm.user_msg_timestamp) as last_message_time,
    MAX(cm.risk_level) as max_risk_level
FROM users u
JOIN chat_messages cm ON u.user_id = cm.user_id
GROUP BY u.user_id, u.username, u.full_name, cm.session_id
ORDER BY MAX(cm.user_msg_timestamp) DESC;

-- View: High-risk sessions
CREATE OR REPLACE VIEW high_risk_sessions AS
SELECT
    user_id,
    session_id,
    COUNT(*) as high_risk_messages,
    MAX(risk_level) as max_risk,
    MAX(user_msg_timestamp) as last_risk_message
FROM chat_messages
WHERE risk_level IN ('high', 'extreme')
GROUP BY user_id, session_id
ORDER BY MAX(user_msg_timestamp) DESC;

-- View: RAG effectiveness
CREATE OR REPLACE VIEW rag_effectiveness AS
SELECT
    intent_label,
    COUNT(*) as total_messages,
    SUM(CASE WHEN rag_used THEN 1 ELSE 0 END) as rag_used_count,
    SUM(CASE WHEN grounded_flag THEN 1 ELSE 0 END) as grounded_count,
    SUM(CASE WHEN rag_benefit_flag THEN 1 ELSE 0 END) as beneficial_count,
    ROUND(AVG(retrieval_score)::numeric, 3) as avg_retrieval_score
FROM chat_messages
GROUP BY intent_label
ORDER BY total_messages DESC;

-- ============================================================
-- STORED PROCEDURES
-- ============================================================

-- Procedure: Get user conversation history
CREATE OR REPLACE FUNCTION get_user_history(p_user_id INT, p_limit INT DEFAULT 50)
RETURNS TABLE (
    message_id INT,
    user_message TEXT,
    assistant_response TEXT,
    timestamp TIMESTAMP,
    risk_level VARCHAR,
    intent_label VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cm.serial_no,
        cm.user_message,
        cm.assistant_response,
        cm.user_msg_timestamp,
        cm.risk_level,
        cm.intent_label
    FROM chat_messages cm
    WHERE cm.user_id = p_user_id
    ORDER BY cm.user_msg_timestamp DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- SAMPLE DATA (for testing)
-- ============================================================

-- Insert sample user (commented out - uncomment to use)
-- INSERT INTO users (username, full_name, email, password_hash, created_at)
-- VALUES ('testuser', 'Test User', 'test@example.com', 'hash_here', CURRENT_TIMESTAMP);

-- ============================================================
-- DATABASE MAINTENANCE
-- ============================================================

-- Vacuum and analyze (run periodically)
-- VACUUM ANALYZE;

-- Check table sizes
-- SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
-- FROM pg_tables
-- WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
-- ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ============================================================
-- END OF SCHEMA
-- ============================================================
