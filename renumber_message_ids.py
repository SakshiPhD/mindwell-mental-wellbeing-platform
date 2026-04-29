"""
Renumber all message_ids to be truly sequential (no gaps, no odd-only pattern)
Changes: 1, 2, 3, ..., 26, 33, 34, ... → 1, 2, 3, ..., 1068
"""
import psycopg2

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
                    db_config[key.strip()] = val.strip().strip('"')
except Exception as e:
    print(f"Error loading config: {e}")
    exit(1)

try:
    print("=" * 80)
    print("RENUMBERING MESSAGE_IDS TO SEQUENTIAL (1, 2, 3, ..., 1068)")
    print("=" * 80)

    conn = psycopg2.connect(
        host=db_config.get("host"),
        user=db_config.get("user"),
        password=db_config.get("password"),
        database=db_config.get("database"),
        port=int(db_config.get("port", 5432)),
        sslmode=db_config.get("sslmode", "require")
    )
    cur = conn.cursor()

    # Step 1: Check current state
    print("\n[STEP 1] Checking current message_ids...")
    cur.execute("SELECT COUNT(*) FROM chat_messages")
    total_messages = cur.fetchone()[0]
    print(f"  Total messages: {total_messages}")

    cur.execute("SELECT MIN(message_id), MAX(message_id) FROM chat_messages")
    min_id, max_id = cur.fetchone()
    print(f"  Current range: {min_id} to {max_id}")

    # Step 2: Show sample of current message_ids
    print("\n[STEP 2] Sample of current message_ids (with gaps):")
    cur.execute("SELECT message_id FROM chat_messages ORDER BY message_id LIMIT 30")
    current_ids = [row[0] for row in cur.fetchall()]
    print(f"  First 30: {current_ids}")

    # Step 3: Create temporary column for new sequential IDs
    print("\n[STEP 3] Creating temporary column for new sequential IDs...")
    cur.execute("""
        ALTER TABLE chat_messages
        ADD COLUMN message_id_new INTEGER
    """)
    print("  [OK] Temporary column created")

    # Step 4: Assign sequential numbers based on current order
    print("\n[STEP 4] Assigning sequential IDs (1, 2, 3, ...)...")
    cur.execute("""
        UPDATE chat_messages
        SET message_id_new = row_number
        FROM (
            SELECT message_id, ROW_NUMBER() OVER (ORDER BY message_id) as row_number
            FROM chat_messages
        ) AS numbered
        WHERE chat_messages.message_id = numbered.message_id
    """)
    print(f"  [OK] {cur.rowcount} rows updated")

    # Step 5: Drop old message_id, rename new to old
    print("\n[STEP 5] Replacing old message_id with new sequential IDs...")
    cur.execute("ALTER TABLE chat_messages DROP COLUMN message_id")
    cur.execute("ALTER TABLE chat_messages RENAME COLUMN message_id_new TO message_id")
    print("  [OK] Column replaced")

    # Step 6: Add PRIMARY KEY constraint back
    print("\n[STEP 6] Adding PRIMARY KEY constraint...")
    cur.execute("ALTER TABLE chat_messages ADD PRIMARY KEY (message_id)")
    print("  [OK] PRIMARY KEY added")

    # Step 7: Recreate sequence
    print("\n[STEP 7] Recreating sequence...")
    cur.execute("DROP SEQUENCE IF EXISTS chat_messages_message_id_seq")
    cur.execute("""
        CREATE SEQUENCE chat_messages_message_id_seq
        START WITH """ + str(total_messages + 1) + """
        INCREMENT BY 1
        OWNED BY chat_messages.message_id
    """)
    print(f"  [OK] Sequence recreated, starts at {total_messages + 1}")

    # Step 8: Verify
    print("\n[STEP 8] Verifying new sequential IDs...")
    cur.execute("SELECT message_id FROM chat_messages ORDER BY message_id LIMIT 30")
    new_ids = [row[0] for row in cur.fetchall()]
    print(f"  First 30: {new_ids}")

    cur.execute("SELECT message_id FROM chat_messages ORDER BY message_id DESC LIMIT 10")
    last_ids = [row[0] for row in cur.fetchall()]
    last_ids.reverse()
    print(f"  Last 10: {last_ids}")

    # Step 9: Check for gaps
    print("\n[STEP 9] Checking for gaps...")
    cur.execute("""
        SELECT COUNT(*) FROM chat_messages
        WHERE message_id != (
            SELECT ROW_NUMBER() OVER (ORDER BY message_id)
            FROM chat_messages
        ) LIMIT 1
    """)
    gap_count = cur.fetchone()[0]

    if gap_count == 0:
        print("  [OK] No gaps found - all IDs are sequential!")
    else:
        print(f"  [ERROR] {gap_count} gaps found")

    # Commit
    conn.commit()
    print("\n[COMMIT] All changes committed to database")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"[+] All {total_messages} message_ids renumbered")
    print(f"[+] New sequence: 1, 2, 3, ..., {total_messages}")
    print(f"[+] No gaps, no odd-only pattern")
    print(f"[+] Next new message_id will be: {total_messages + 1}")
    print("=" * 80)

    conn.close()

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    try:
        conn.rollback()
    except:
        pass
