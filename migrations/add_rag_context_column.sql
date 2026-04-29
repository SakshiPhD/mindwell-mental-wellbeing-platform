-- Migration: Add RAG context tracking to chat_messages
-- Date: 2026-04-11
-- Purpose: Store which RAG chunks were used for each message (doc_id, source, chunk_text)

ALTER TABLE chat_messages
ADD COLUMN IF NOT EXISTS rag_context JSONB;

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_chat_messages_rag_context
ON chat_messages USING GIN (rag_context);

-- Log completion
DO $$
BEGIN
  RAISE NOTICE 'Migration complete: rag_context column added to chat_messages';
END $$;
