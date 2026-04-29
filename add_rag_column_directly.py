#!/usr/bin/env python3
"""
Direct script to add rag_context column to chat_messages table.
Run this if the column doesn't appear after app restart.
"""

import psycopg2
import streamlit as st
import sys

# Load secrets from Streamlit config
try:
    # Try to load from Streamlit secrets
    if hasattr(st, 'secrets') and 'postgres' in st.secrets:
        creds = st.secrets["postgres"]
        host = creds.get("host")
        port = creds.get("port", 5432)
        user = creds.get("user")
        password = creds.get("password")
        database = creds.get("database")
    else:
        print("❌ Streamlit secrets not available. Please run this from Streamlit app context.")
        print("   Or manually set: host, port, user, password, database")
        sys.exit(1)
except Exception as e:
    print(f"❌ Error loading secrets: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("Adding rag_context column to chat_messages")
print("="*60)
print(f"Database: {database}@{host}:{port}")
print()

try:
    # Connect to database
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database
    )
    cur = conn.cursor()

    # Check if column already exists
    print("1. Checking if rag_context column already exists...")
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'chat_messages' AND column_name = 'rag_context'
    """)
    exists = cur.fetchone()[0]

    if exists:
        print("   ✅ rag_context column already exists!")
    else:
        print("   ❌ rag_context column not found. Adding it now...")

        # Add the column
        cur.execute("""
            ALTER TABLE chat_messages
            ADD COLUMN IF NOT EXISTS rag_context JSONB;
        """)
        print("   ✅ Column added successfully!")

    # Create index
    print("\n2. Creating GIN index for faster queries...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_messages_rag_context
        ON chat_messages USING GIN (rag_context);
    """)
    print("   ✅ Index created/verified!")

    # Verify
    print("\n3. Verifying column...")
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'chat_messages' AND column_name = 'rag_context'
    """)
    col = cur.fetchone()
    if col:
        col_name, data_type = col
        print(f"   ✅ Confirmed: {col_name} ({data_type})")
    else:
        print("   ❌ Verification failed!")
        conn.rollback()
        cur.close()
        conn.close()
        sys.exit(1)

    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "="*60)
    print("✅ SUCCESS! rag_context column is ready.")
    print("="*60)
    print("\nYou can now:")
    print("  1. Query RAG data: SELECT rag_context FROM chat_messages")
    print("  2. See which source was used:")
    print("     SELECT jsonb_array_elements(rag_context)->>'source'")
    print("     FROM chat_messages WHERE rag_context IS NOT NULL")
    print("\n" + "="*60 + "\n")

except psycopg2.Error as e:
    print(f"\n❌ Database error: {e}")
    try:
        conn.rollback()
        cur.close()
        conn.close()
    except:
        pass
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)
