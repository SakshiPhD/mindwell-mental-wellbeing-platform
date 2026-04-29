#!/usr/bin/env python3
"""
Quick test to verify database sequence fix is working.
"""
import sys
sys.path.insert(0, r'c:\Users\harsh\OneDrive\Desktop\23march_healthawareness')

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

from dotenv import load_dotenv
load_dotenv()

from database import get_pooled_connection
import uuid
from datetime import datetime

def test_sequence_fix():
    """Test if we can insert messages without duplicate key errors."""
    print("\n=== Database Sequence Fix Test ===\n")

    # Get a connection
    with get_pooled_connection() as conn:
        if not conn:
            print("❌ Failed to get database connection")
            return False

        cur = conn.cursor()

        try:
            # Check current sequence state
            print("1️⃣  Checking sequence state...")
            cur.execute("""
                SELECT sequence_name, last_value, max_value, increment_by
                FROM information_schema.sequences
                WHERE sequence_name IN ('chat_messages_message_id_seq', 'chat_messages_serial_no_seq')
                ORDER BY sequence_name
            """)
            seqs = cur.fetchall()

            if seqs:
                for seq_name, last_val, max_val, inc_by in seqs:
                    print(f"   ✓ {seq_name}: last_value={last_val}, increment={inc_by}")
            else:
                print("   ⚠️  No sequences found - they may have been dropped")

            # Check max IDs in table
            print("\n2️⃣  Checking max IDs in chat_messages table...")
            cur.execute("SELECT COUNT(*) as total_rows, MAX(message_id) as max_msg_id, MAX(serial_no) as max_serial FROM chat_messages")
            total, max_msg_id, max_serial = cur.fetchone()
            print(f"   ✓ Total rows: {total}")
            print(f"   ✓ Max message_id: {max_msg_id}")
            print(f"   ✓ Max serial_no: {max_serial}")

            # Try a test insert
            print("\n3️⃣  Testing INSERT with new SERIAL...")
            test_user_id = 999  # Test user ID
            test_session_id = str(uuid.uuid4())

            cur.execute("""
                INSERT INTO chat_messages
                (
                    user_id, session_id,
                    user_message, assistant_response,
                    user_msg_timestamp, bot_msg_timestamp, latency_seconds,
                    risk_level, safety_action,
                    intent_label, response_mode, memory_used, memory_type,
                    escalation_flag, final_reply_agent, fallback_triggered,
                    rag_used
                )
                VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING message_id, serial_no
            """,
            (
                test_user_id, test_session_id,
                "[TEST] User message", "[TEST] Assistant response",
                datetime.now(), datetime.now(), 0.5,
                "low", "normal",
                "test", "supportive", False, "",
                False, "coach", False,
                False,
            ))

            result = cur.fetchone()
            if result:
                new_msg_id, new_serial_no = result
                print(f"   ✅ INSERT successful!")
                print(f"      - Assigned message_id: {new_msg_id}")
                print(f"      - Assigned serial_no: {new_serial_no}")
                conn.commit()

                # Clean up test data
                cur.execute("DELETE FROM chat_messages WHERE user_id = %s AND session_id = %s", (test_user_id, test_session_id))
                conn.commit()
                print(f"   ✓ Cleaned up test data")

                return True
            else:
                print("   ❌ INSERT returned no result")
                return False

        except Exception as e:
            print(f"   ❌ Error during test: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            cur.close()

if __name__ == "__main__":
    success = test_sequence_fix()
    print("\n" + "="*40)
    if success:
        print("✅ Database sequence fix is working!")
    else:
        print("❌ Database still has issues")
    print("="*40 + "\n")
