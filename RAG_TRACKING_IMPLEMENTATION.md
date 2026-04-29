# RAG Context Tracking Implementation Summary

## What Was Changed

### 1. **Database Schema** (`database.py`)
- ✅ Added `rag_context JSONB` column to `chat_messages` table
- This stores exactly which chunks were used and from which source

### 2. **New RAG Function** (`rag.py`)
- ✅ Added `retrieve_relevant_chunks_with_metadata()` function
- Returns: `(chunks, metadata_list)` where metadata contains:
  - `doc_id` — RAG document ID
  - `source` — Where the chunk came from (e.g., "session_summary", "extracted_facts")
  - `chunk_text` — The actual text chunk (for audit trail)

### 3. **Data Collection** (`pages.py`)
- ✅ After `fetch_all_user_context()`, calls new RAG function
- Collects metadata with chunk source and document ID
- Prints debug info: `[RAG DEBUG] RAG METADATA COLLECTED`

### 4. **Data Storage** (`pages.py` + `database.py`)
- ✅ Passes `rag_context` to `save_chat_message()`
- Stored as JSONB in database for easy querying

---

## Data Flow

```
User sends message
    ↓
fetch_all_user_context() → gets RAG chunks
    ↓
retrieve_relevant_chunks_with_metadata() → collects doc_id, source, text
    ↓
run_care_pipeline() → LLM generates response
    ↓
save_chat_message(..., rag_context=metadata)
    ↓
DATABASE: chat_messages.rag_context = 
[
  {"doc_id": 5, "source": "session_summary", "chunk_text": "..."},
  {"doc_id": 12, "source": "extracted_facts", "chunk_text": "..."}
]
```

---

## What You Can Now Query from Database

### ✅ See which chunk was used for a specific message
```sql
SELECT rag_context 
FROM chat_messages 
WHERE message_id = 100;
```

### ✅ See where response came from (which source document)
```sql
SELECT 
  user_message,
  jsonb_array_elements(rag_context)->>'source' as source,
  jsonb_array_elements(rag_context)->>'doc_id' as doc_id
FROM chat_messages 
WHERE user_id = 123;
```

### ✅ Find which sources are most helpful
```sql
SELECT 
  jsonb_array_elements(rag_context)->>'source' as source,
  COUNT(*) as times_used
FROM chat_messages
WHERE rag_context IS NOT NULL
GROUP BY source
ORDER BY COUNT(*) DESC;
```

### ✅ Compare latency: with RAG vs. without RAG
```sql
SELECT 
  CASE WHEN rag_context IS NOT NULL THEN 'WITH RAG' 
       ELSE 'NO RAG' END,
  AVG(latency_seconds)
FROM chat_messages
GROUP BY 1;
```

---

## Implementation Details

### Column Structure (JSONB)
```json
rag_context: [
  {
    "doc_id": integer,           -- rag_documents.doc_id
    "source": string,            -- rag_documents.source (e.g., "session_summary")
    "chunk_text": string         -- First 500 chars of chunk (for reference)
  },
  ...
]
```

### Key Design Decisions

| Decision | Why |
|----------|-----|
| Store `doc_id` + `source` | Can always join to `rag_documents` table if needed for full chunk |
| Store chunk preview (500 chars) | Audit trail - see exactly what context was available |
| Single JSONB column | Avoids table bloat, simple queries with `jsonb_*` operators |
| No memory_injected storage | Too large (2KB+), not useful for queries |
| GIN index on rag_context | Fast JSONB queries |

---

## How to Use

### Step 1: Apply Migration (if needed)
```bash
# Run the migration SQL:
psql -U $DB_USER -d $DB_NAME -f migrations/add_rag_context_column.sql
```

### Step 2: Code automatically collects RAG data
```
No changes needed on your end!
- When user sends message → RAG metadata is collected
- When response is saved → rag_context is stored in database
```

### Step 3: Query the database
```sql
-- See what RAG was used
SELECT user_message, rag_context 
FROM chat_messages 
WHERE user_id = YOUR_USER_ID 
ORDER BY message_id DESC LIMIT 5;
```

---

## Testing

### 1. Check migration was applied
```sql
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'chat_messages' AND column_name = 'rag_context';
```
✅ Should return one row

### 2. Send a test message in the app
- Watch terminal for: `[RAG DEBUG] RAG METADATA COLLECTED`

### 3. Query the database
```sql
SELECT rag_context FROM chat_messages 
WHERE user_id = YOUR_ID 
ORDER BY message_id DESC LIMIT 1;
```
✅ Should show JSON array with chunks

---

## Example Query Output

```
user_message: "How do I handle anxiety at work?"

rag_context: [
  {
    "doc_id": 5,
    "source": "session_summary",
    "chunk_text": "User mentioned anxiety during presentations. Tried breathing exercises with moderate success..."
  },
  {
    "doc_id": 12,
    "source": "extracted_facts",
    "chunk_text": "User works in IT sector. High-stress environment. Sleep often affected by work..."
  }
]
```

Now you can see: **This response was based on chunks 5 and 12 from session_summary and extracted_facts sources.**

---

## Monitoring & Analytics

### Which sources help most?
```sql
SELECT source, COUNT(*) FROM (
  SELECT jsonb_array_elements(rag_context)->>'source' as source
  FROM chat_messages WHERE rag_context IS NOT NULL
) GROUP BY source ORDER BY COUNT(*) DESC;
```

### Average response quality by RAG usage
```sql
SELECT 
  CASE WHEN rag_context IS NULL THEN 'No RAG'
       ELSE 'With RAG' END as rag_status,
  AVG(latency_seconds) as avg_latency
FROM chat_messages
GROUP BY rag_status;
```

---

## Files Modified

1. **database.py**
   - Added `rag_context` column to migration
   - Updated `save_chat_message()` to accept and store `rag_context`

2. **rag.py**
   - Added `retrieve_relevant_chunks_with_metadata()` function
   - Returns chunks + metadata (doc_id, source, chunk_text)

3. **pages.py**
   - Calls new metadata function after `fetch_all_user_context()`
   - Passes metadata to `save_chat_message()`

4. **migrations/add_rag_context_column.sql** (NEW)
   - SQL migration to add column

5. **RAG_DATABASE_QUERIES.md** (NEW)
   - 10+ example queries for tracking RAG usage

---

## Next Steps (Optional)

1. **Run migration** on production database
2. **Monitor logs** for `[RAG DEBUG]` messages
3. **Query database** using provided SQL examples
4. **Analyze** which sources are most helpful
5. **Optimize** RAG by removing low-value sources if needed

---

## Troubleshooting

**Q: My existing messages don't have rag_context?**
- A: Normal! Only new messages will have it. Old messages predate the feature.

**Q: rag_context is NULL for new messages?**
- A: RAG retrieval may have failed. Check app logs for errors.

**Q: Query returns empty JSONB?**
- A: No chunks matched the query. See debug logs for details.

**Q: How do I see the full chunk text?**
- A: Join to `rag_documents` table using `doc_id`:
```sql
SELECT cd.content 
FROM chat_messages cm,
  jsonb_array_elements(cm.rag_context) as elem,
  rag_documents cd
WHERE cm.message_id = 100
  AND cd.doc_id = (elem->>'doc_id')::integer;
```

---

## Summary

✅ **1 column added** to track which chunks were used  
✅ **doc_id + source** stored for full audit trail  
✅ **Easy to query** using standard JSONB operators  
✅ **Zero bloat** — only storing essential data  
✅ **Developer-friendly** — automatic collection, manual querying  

Now you can answer: **"Where did this response come from? Which document provided this information?"**
