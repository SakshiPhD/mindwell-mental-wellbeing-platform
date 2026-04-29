#!/usr/bin/env python3
"""
Verification script for RAG context tracking implementation.
Run this to ensure everything is working correctly.
"""

import sys
import logging
from database import get_pooled_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_column_exists():
    """Verify rag_context column exists in chat_messages."""
    with get_pooled_connection() as conn:
        if not conn:
            print("❌ Cannot connect to database")
            return False

        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'chat_messages'
                  AND column_name = 'rag_context'
            """)
            row = cur.fetchone()
            if row:
                col_name, data_type = row
                if data_type == "jsonb":
                    print(f"✅ Column '{col_name}' exists with type '{data_type}'")
                    return True
                else:
                    print(f"⚠️  Column exists but type is '{data_type}' (expected 'jsonb')")
                    return False
            else:
                print("❌ Column 'rag_context' not found in chat_messages")
                return False
        finally:
            cur.close()


def check_index_exists():
    """Verify GIN index was created for rag_context."""
    with get_pooled_connection() as conn:
        if not conn:
            return False

        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'chat_messages'
                  AND indexname LIKE '%rag%'
            """)
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    print(f"✅ Index found: {row[0]}")
                return True
            else:
                print("⚠️  No RAG index found (performance may be slower)")
                return False
        finally:
            cur.close()


def check_sample_data():
    """Check if any messages have rag_context data."""
    with get_pooled_connection() as conn:
        if not conn:
            return False

        cur = conn.cursor()
        try:
            # Count messages with rag_context
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(*) FILTER (WHERE rag_context IS NOT NULL) as with_rag
                FROM chat_messages
                LIMIT 1
            """)
            total, with_rag = cur.fetchone()
            print(f"📊 Chat messages: {total} total, {with_rag} with RAG context")

            if with_rag > 0:
                # Show a sample
                cur.execute("""
                    SELECT message_id, user_id, user_message,
                           jsonb_array_length(rag_context) as num_chunks
                    FROM chat_messages
                    WHERE rag_context IS NOT NULL
                    ORDER BY message_id DESC
                    LIMIT 1
                """)
                msg_id, user_id, user_msg, chunks = cur.fetchone()
                print(f"✅ Sample: Message {msg_id} (user {user_id}) has {chunks} chunks")
                print(f"   User said: {user_msg[:60]}...")
                return True
            else:
                print("⚠️  No messages with rag_context yet (run the app first)")
                return False
        finally:
            cur.close()


def test_query():
    """Test a complex JSONB query."""
    with get_pooled_connection() as conn:
        if not conn:
            return False

        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT
                    jsonb_array_elements(rag_context)->>'source' as source,
                    COUNT(*) as count
                FROM chat_messages
                WHERE rag_context IS NOT NULL
                GROUP BY source
                LIMIT 5
            """)
            rows = cur.fetchall()
            if rows:
                print("✅ JSONB query works! Sources used:")
                for source, count in rows:
                    print(f"   - {source}: {count} times")
                return True
            else:
                print("⚠️  Query works but no RAG sources found yet")
                return False
        except Exception as e:
            print(f"❌ JSONB query failed: {e}")
            return False
        finally:
            cur.close()


def main():
    print("\n" + "="*60)
    print("RAG Context Tracking Verification")
    print("="*60 + "\n")

    results = []

    print("1. Checking database column...")
    results.append(check_column_exists())
    print()

    print("2. Checking database index...")
    results.append(check_index_exists())
    print()

    print("3. Checking sample data...")
    results.append(check_sample_data())
    print()

    print("4. Testing JSONB queries...")
    results.append(test_query())
    print()

    # Summary
    passed = sum(results)
    total = len(results)

    print("="*60)
    print(f"Summary: {passed}/{total} checks passed")
    print("="*60)

    if passed == total:
        print("\n✅ All checks passed! RAG tracking is ready.")
        return 0
    elif passed >= 2:
        print("\n⚠️  Some checks passed. See above for details.")
        return 1
    else:
        print("\n❌ Most checks failed. Run migration first:")
        print("   psql -U user -d dbname -f migrations/add_rag_context_column.sql")
        return 2


if __name__ == "__main__":
    sys.exit(main())
