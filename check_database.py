"""
Direct database diagnostic - no Streamlit dependency
"""
import psycopg2
import os
import sys

# Set encoding to UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Load secrets from .streamlit/secrets.toml
db_config = {}
try:
    with open(".streamlit/secrets.toml", "r") as f:
        section = ""
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
            elif "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                if section == "postgres":
                    key = key.strip()
                    val = val.strip().strip('"')
                    db_config[key] = val
except Exception as e:
    print(f"Warning: Could not load secrets: {e}")
    pass

try:
    conn = psycopg2.connect(
        host=db_config.get("host", os.getenv("db_host", "pg.neon.tech")),
        user=db_config.get("user", os.getenv("db_user")),
        password=db_config.get("password", os.getenv("db_password")),
        database=db_config.get("database", os.getenv("db_name", "neondb")),
        port=int(db_config.get("port", 5432)),
        sslmode=db_config.get("sslmode", "require")
    )
    cur = conn.cursor()

    print("=" * 80)
    print("DATABASE DIAGNOSTIC REPORT")
    print("=" * 80)

    # ==================== SEQUENCES ====================
    print("\n[1] ALL SEQUENCES IN DATABASE")
    print("-" * 80)
    try:
        # Use pg_sequences instead of information_schema.sequences (more reliable)
        cur.execute("""
            SELECT sequencename, last_value, increment_by
            FROM pg_sequences
            WHERE schemaname = 'public'
            ORDER BY sequencename
        """)
        sequences = cur.fetchall()
        if sequences:
            for seq_name, last_val, incr_by in sequences:
                incr_str = f"increment={incr_by}" if incr_by else "unknown"
                last_str = f"last={last_val}" if last_val is not None else "unknown"
                print(f"{seq_name:45} | {last_str:15} | {incr_str}")
        else:
            print("No sequences found")
    except Exception as seq_err:
        print(f"Could not query sequences: {seq_err}")
        # Reset transaction
        try:
            conn.rollback()
        except:
            pass

    # ==================== chat_messages TABLE ====================
    print("\n\n[2] CHAT_MESSAGES TABLE ANALYSIS")
    print("-" * 80)

    # Schema
    print("\nTable Schema:")
    try:
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'chat_messages'
            ORDER BY ordinal_position
        """)
        for col_name, data_type, is_nullable in cur.fetchall():
            nullable_str = "nullable" if is_nullable == "YES" else "NOT NULL"
            print(f"  {col_name:25} {data_type:20} {nullable_str}")
    except Exception as col_err:
        print(f"Could not query columns: {col_err}")

    # Row count
    cur.execute("SELECT COUNT(*) FROM chat_messages")
    total_rows = cur.fetchone()[0]
    print(f"\nTotal rows: {total_rows}")

    if total_rows > 0:
        # Message ID pattern
        print("\nMessage ID Pattern Analysis:")
        cur.execute("""
            SELECT message_id, serial_no
            FROM chat_messages
            ORDER BY message_id
            LIMIT 100
        """)
        rows = cur.fetchall()
        msg_ids = [r[0] for r in rows]
        serial_nos = [r[1] for r in rows]

        print(f"  First 20 message_ids: {msg_ids[:20]}")
        print(f"  First 20 serial_nos:  {serial_nos[:20]}")

        # Check odd/even pattern
        is_all_odd = all(mid % 2 == 1 for mid in msg_ids)
        is_all_even = all(mid % 2 == 0 for mid in msg_ids)

        if is_all_odd:
            print(f"\n  [ERROR] ISSUE: ALL message_ids are ODD!")
            print(f"     Sample: {msg_ids[:10]}")
            print(f"     This suggests sequence is incrementing by 2 instead of 1")

            # Find the pattern
            if len(msg_ids) > 1:
                diffs = [msg_ids[i+1] - msg_ids[i] for i in range(min(10, len(msg_ids)-1))]
                print(f"     Differences between consecutive IDs: {set(diffs)}")

        elif is_all_even:
            print(f"\n  [ERROR] ISSUE: ALL message_ids are EVEN!")
            print(f"     Sample: {msg_ids[:10]}")
        else:
            print(f"\n  [OK] Message IDs look normal (mixed odd/even)")

        # Check for gaps
        print("\nGap Detection:")
        gaps = []
        for i in range(len(msg_ids) - 1):
            if msg_ids[i+1] - msg_ids[i] != 1:
                gaps.append((msg_ids[i], msg_ids[i+1], msg_ids[i+1] - msg_ids[i]))

        if gaps:
            print(f"  [ERROR] FOUND {len(gaps)} GAPS in message_id sequence!")
            for before, after, gap_size in gaps[:20]:
                print(f"     Gap: {before} --> {after} (skipped {gap_size - 1} values)")
        else:
            print(f"  [OK] No gaps - sequence is continuous")

        # Check serial_no
        print("\nSerial Number Sequencing:")
        is_seq = all(serial_nos[i] == i + 1 for i in range(min(len(serial_nos), 20)))
        if is_seq:
            print(f"  [OK] serial_nos are properly sequential (1, 2, 3, ...)")
        else:
            print(f"  [WARN] serial_nos might have issues")
            print(f"     Values: {serial_nos[:20]}")

    # ==================== chat_analysis TABLE ====================
    print("\n\n[3] CHAT_ANALYSIS TABLE ANALYSIS")
    print("-" * 80)

    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'chat_analysis'
        ORDER BY ordinal_position
    """)
    analysis_cols = cur.fetchall()
    col_names = [col[0] for col in analysis_cols]

    print("\nColumns in chat_analysis:")
    for col_name, data_type in analysis_cols:
        print(f"  {col_name:25} {data_type}")

    has_visible = "visible_serial_no" in col_names
    has_serial = "serial_no" in col_names

    print(f"\nColumn Status:")
    if has_visible:
        print(f"  [ERROR] 'visible_serial_no' EXISTS (should be renamed to 'serial_no')")
    else:
        print(f"  [OK] 'visible_serial_no' does NOT exist")

    if has_serial:
        print(f"  [OK] 'serial_no' EXISTS")
    else:
        print(f"  [ERROR] 'serial_no' does NOT exist")

    if has_visible and has_serial:
        print(f"  [WARN] BOTH columns exist! Need cleanup.")

    # Row count
    cur.execute("SELECT COUNT(*) FROM chat_analysis")
    analysis_rows = cur.fetchone()[0]
    print(f"\nTotal rows: {analysis_rows}")

    # ==================== ALL TABLES ====================
    print("\n\n[4] ALL TABLES AND ROW COUNTS")
    print("-" * 80)

    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = cur.fetchall()

    for table_name, in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            print(f"  {table_name:30} {count:8} rows")
        except:
            print(f"  {table_name:30} [error reading]")

    # ==================== RECOMMENDATIONS ====================
    print("\n\n[5] DIAGNOSIS & RECOMMENDATIONS")
    print("=" * 80)

    if is_all_odd:
        print("\n[ERROR] PRIMARY ISSUE FOUND: message_id sequence is incrementing by 2")
        print("\nROOT CAUSE:")
        print("  The sequence 'chat_messages_message_id_seq' has INCREMENT BY 2 instead of 1")
        print("  This could be from:")
        print("    1. Corrupted sequence definition")
        print("    2. Manual creation with wrong increment value")
        print("    3. Failed migration that altered the sequence")

        print("\nFIX COMMANDS:")
        print("\n  -- Check current sequence definition")
        print("  SELECT * FROM pg_sequences WHERE sequencename = 'chat_messages_message_id_seq';")
        print("\n  -- Reset sequence to increment by 1")
        print("  ALTER SEQUENCE chat_messages_message_id_seq INCREMENT BY 1;")
        print("\n  -- Reset last_value to current max + 1")
        print("  SELECT setval('chat_messages_message_id_seq',")
        print("    COALESCE((SELECT MAX(message_id) FROM chat_messages), 0) + 1);")

    if has_visible and not has_serial:
        print("\n[WARN] SECONDARY ISSUE: chat_analysis needs column rename")
        print("\nFIX COMMAND:")
        print("  ALTER TABLE chat_analysis RENAME COLUMN visible_serial_no TO serial_no;")

    print("\n" + "=" * 80)

    conn.close()

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
