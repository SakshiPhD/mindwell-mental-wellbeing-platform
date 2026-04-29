# RAG Context Tracking in Database

## Schema Change

**Column Added to `chat_messages` table:**
- `rag_context JSONB` — Stores array of chunks used in the conversation

**Structure of rag_context:**
```json
[
  {
    "doc_id": 5,
    "source": "session_summary",
    "chunk_text": "User mentioned having anxiety about presentations last Tuesday. They tried breathing exercises but..."
  },
  {
    "doc_id": 12,
    "source": "extracted_facts",
    "chunk_text": "Works in IT sector. Has 5 years experience..."
  },
  {
    "doc_id": null,
    "source": "unknown",
    "chunk_text": "..."
  }
]
```

---

## Database Queries to Track RAG Usage

### 1. **Show all messages with RAG chunks for a user**
```sql
SELECT 
  message_id,
  user_msg_timestamp,
  user_message,
  jsonb_array_length(rag_context) as num_chunks_used,
  rag_context
FROM chat_messages
WHERE user_id = 123
  AND rag_context IS NOT NULL
ORDER BY user_msg_timestamp DESC
LIMIT 10;
```

### 2. **Show only messages WITH RAG context (not empty)**
```sql
SELECT 
  message_id,
  user_message,
  user_msg_timestamp,
  rag_context
FROM chat_messages
WHERE user_id = 123
  AND rag_context IS NOT NULL
  AND jsonb_array_length(rag_context) > 0
ORDER BY user_msg_timestamp DESC;
```

### 3. **Extract which SOURCE was used most**
```sql
SELECT 
  jsonb_array_elements(rag_context)->>'source' as source,
  COUNT(*) as num_times_used
FROM chat_messages
WHERE user_id = 123
  AND rag_context IS NOT NULL
GROUP BY source
ORDER BY COUNT(*) DESC;
```

### 4. **See actual chunk text that was used**
```sql
SELECT 
  message_id,
  user_message,
  jsonb_array_elements(rag_context)->>'source' as source,
  jsonb_array_elements(rag_context)->>'doc_id' as doc_id,
  jsonb_array_elements(rag_context)->>'chunk_text' as chunk_text,
  user_msg_timestamp
FROM chat_messages
WHERE user_id = 123
  AND rag_context IS NOT NULL
ORDER BY user_msg_timestamp DESC;
```

### 5. **Find which doc_ids are most frequently used**
```sql
SELECT 
  jsonb_array_elements(rag_context)->>'doc_id' as doc_id,
  jsonb_array_elements(rag_context)->>'source' as source,
  COUNT(*) as usage_count
FROM chat_messages
WHERE rag_context IS NOT NULL
GROUP BY doc_id, source
ORDER BY COUNT(*) DESC
LIMIT 20;
```

### 6. **Show messages where RAG was NOT used (rag_context is NULL or empty)**
```sql
SELECT 
  message_id,
  user_message,
  user_msg_timestamp,
  assistant_response
FROM chat_messages
WHERE user_id = 123
  AND (rag_context IS NULL OR jsonb_array_length(rag_context) = 0)
ORDER BY user_msg_timestamp DESC
LIMIT 10;
```

### 7. **Find a specific RAG document and see where it was used**
```sql
SELECT 
  cm.message_id,
  cm.user_id,
  cm.user_message,
  cm.user_msg_timestamp,
  (elem->>'doc_id')::integer as doc_id
FROM chat_messages cm,
  jsonb_array_elements(cm.rag_context) as elem
WHERE (elem->>'doc_id')::integer = 5  -- Replace with target doc_id
  AND cm.rag_context IS NOT NULL
ORDER BY cm.user_msg_timestamp DESC;
```

### 8. **Session-level RAG analytics**
```sql
SELECT 
  session_id,
  COUNT(*) as total_messages,
  COUNT(*) FILTER (WHERE rag_context IS NOT NULL) as messages_with_rag,
  COUNT(*) FILTER (WHERE jsonb_array_length(rag_context) > 0) as messages_with_chunks,
  ROUND(100.0 * COUNT(*) FILTER (WHERE jsonb_array_length(rag_context) > 0) / COUNT(*), 2) as rag_usage_percent
FROM chat_messages
WHERE user_id = 123
GROUP BY session_id
ORDER BY session_id DESC;
```

### 9. **Compare response quality by RAG usage**
```sql
SELECT 
  CASE 
    WHEN rag_context IS NULL OR jsonb_array_length(rag_context) = 0 THEN 'NO RAG'
    WHEN jsonb_array_length(rag_context) = 1 THEN '1 CHUNK'
    WHEN jsonb_array_length(rag_context) = 2 THEN '2 CHUNKS'
    ELSE '3+ CHUNKS'
  END as rag_usage,
  COUNT(*) as count,
  ROUND(AVG(latency_seconds), 2) as avg_latency_sec
FROM chat_messages
WHERE user_id = 123
GROUP BY rag_usage
ORDER BY count DESC;
```

### 10. **Export RAG audit trail for debugging**
```sql
SELECT 
  cm.message_id,
  cm.session_id,
  cm.user_id,
  cm.user_message,
  cm.assistant_response,
  cm.user_msg_timestamp,
  cm.latency_seconds,
  jsonb_pretty(cm.rag_context) as rag_chunks_used,
  cm.risk_level,
  cm.memory_used
FROM chat_messages cm
WHERE cm.user_id = 123
  AND cm.rag_context IS NOT NULL
ORDER BY cm.user_msg_timestamp DESC
LIMIT 50;
```

---

## Application Code Impact

### In Python (pages.py):

```python
# After run_care_pipeline, RAG metadata is collected:
rag_metadata_for_db = [
    {
        "doc_id": 5,
        "source": "session_summary",
        "chunk_text": "..."
    },
    ...
]

# Passed to save_chat_message:
save_chat_message(
    ...,
    rag_context=rag_metadata_for_db,  # NEW PARAMETER
)
```

### In Database (database.py):

```python
def save_chat_message(..., rag_context=None):
    # rag_context is converted to JSON and stored as JSONB
    cur.execute(
        "INSERT INTO chat_messages ... rag_context ... VALUES ... %s::jsonb",
        (..., rag_context_json)
    )
```

---

## Verification Steps

### 1. Check the migration was applied:
```sql
SELECT column_name, data_type 
FROM information_schema.columns
WHERE table_name = 'chat_messages' AND column_name = 'rag_context';
```
Should return: `rag_context | jsonb`

### 2. Check index was created:
```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'chat_messages' AND indexname LIKE '%rag%';
```

### 3. Test with a real message:
```sql
-- After a user sends a message, run:
SELECT user_message, rag_context FROM chat_messages 
WHERE user_id = 123 
ORDER BY message_id DESC LIMIT 1;
```

---

## Performance Notes

- **Index**: `GIN (rag_context)` allows fast queries on JSONB array
- **Storage**: ~200-500 bytes per message (depends on chunk size)
- **Query Speed**: JSONB queries are fast with proper indexing
- **Retention**: Consider archiving old messages if storage becomes concern

---

## Troubleshooting

**Q: rag_context is NULL for recent messages?**
- A: RAG retrieval may have failed or no chunks matched. Check application logs for `[RAG DEBUG]` messages.

**Q: Can't parse the JSONB?**
- A: Use `jsonb_pretty(rag_context)` to format nicely.

**Q: Want to clear old RAG data?**
```sql
UPDATE chat_messages 
SET rag_context = NULL 
WHERE user_msg_timestamp < NOW() - INTERVAL '30 days'
  AND user_id = 123;
```
