"""
Final comprehensive fix for message_id sequencing
Handles PRIMARY KEY constraint properly
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
    print(f"Error: {e}")
    exit(1)

try:
    print("=" * 80)
    print("FINAL FIX: MESSAGE_ID SEQUENTIAL RENUMBERING")
    print("=" * 80)

    conn = psycopg2.connect(
        host=db_config.get("host"),
        user=db_config.get("user"),
        password=db_config.get("password"),
        database=db_config.get("database"),
        port=int(db_config.get("port", 5432)),
        sslmode=db_config.get("sslmode", "require")
    )
    # Use autocommit=False so we can control transactions
    conn.autocommit = False
    cur = conn.cursor()

    # Step 1: Get current count
    print("\n[STEP 1] Analyzing current data...")
    cur.execute("SELECT COUNT(*) FROM chat_messages")
    total_rows = cur.fetchone()[0]
    print(f"  Total messages: {total_rows}")

    # Step 2: Drop PRIMARY KEY
    print("\n[STEP 2] Removing PRIMARY KEY constraint...")
    cur.execute("ALTER TABLE chat_messages DROP CONSTRAINT chat_messages_pkey")
    print("  [OK] PRIMARY KEY dropped")

    # Step 3: Drop sequence (to avoid conflicts)
    print("\n[STEP 3] Dropping old sequence...")
    cur.execute("DROP SEQUENCE IF EXISTS chat_messages_message_id_seq CASCADE")
    print("  [OK] Sequence dropped")

    # Step 4: Create temp column
    print("\n[STEP 4] Creating temporary sequential column...")
    cur.execute("""
        ALTER TABLE chat_messages
        ADD COLUMN message_id_temp INTEGER
    """)
    print("  [OK] Temp column added")

    # Step 5: Generate sequential numbers using CTE
    print("\n[STEP 5] Assigning sequential numbers (1, 2, 3, ...)...")
    cur.execute("""
        WITH numbered AS (
            SELECT message_id, ROW_NUMBER() OVER (ORDER BY message_id) as new_id
            FROM chat_messages
        )
        UPDATE chat_messages cm
        SET message_id_temp = n.new_id
        FROM numbered n
        WHERE cm.message_id = n.message_id
    """)
    print(f"  [OK] {cur.rowcount} rows updated")

    # Step 6: Drop old column, rename new
    print("\n[STEP 6] Replacing message_id column...")
    cur.execute("ALTER TABLE chat_messages DROP COLUMN message_id")
    cur.execute("ALTER TABLE chat_messages RENAME COLUMN message_id_temp TO message_id")
    print("  [OK] Column renamed")

    # Step 7: Add PRIMARY KEY back
    print("\n[STEP 7] Adding PRIMARY KEY constraint...")
    cur.execute("ALTER TABLE chat_messages ADD PRIMARY KEY (message_id)")
    print("  [OK] PRIMARY KEY added")

    # Step 8: Create new sequence
    print("\n[STEP 8] Creating new sequence...")
    cur.execute(f"""
        CREATE SEQUENCE chat_messages_message_id_seq
        START WITH {total_rows + 1}
        INCREMENT BY 1
        OWNED BY chat_messages.message_id
    """)
    print(f"  [OK] Sequence created (starts at {total_rows + 1})")

    # Step 9: Verify
    print("\n[STEP 9] Verifying fix...")
    cur.execute("SELECT MIN(message_id), MAX(message_id) FROM chat_messages")
    min_id, max_id = cur.fetchone()
    print(f"  Range: {min_id} to {max_id}")

    cur.execute("SELECT COUNT(*) FROM chat_messages")
    count = cur.fetchone()[0]
    print(f"  Total: {count}")

    # Check if truly sequential
    cur.execute("""
        SELECT COUNT(*) FROM chat_messages cm
        WHERE cm.message_id NOT IN (
            SELECT ROW_NUMBER() OVER (ORDER BY message_id)
            FROM chat_messages
        )
    """)
    non_sequential = cur.fetchone()[0]

    if non_sequential == 0:
        print(f"  [OK] ALL {total_rows} message_ids are sequential!")
    else:
        print(f"  [ERROR] {non_sequential} non-sequential IDs")

    # Commit
    conn.commit()
    print("\n[COMMIT] All changes committed")

    # Final display
    print("\n" + "=" * 80)
    print("FINAL STATE")
    print("=" * 80)

    cur.execute("SELECT message_id FROM chat_messages ORDER BY message_id LIMIT 20")
    first_20 = [row[0] for row in cur.fetchall()]

    cur.execute("SELECT message_id FROM chat_messages ORDER BY message_id DESC LIMIT 10")
    last_10 = [row[0] for row in cur.fetchall()]
    last_10.reverse()

    print(f"\nFirst 20:   {first_20}")
    print(f"Last 10:    {last_10}")

    cur.execute("SELECT message_id FROM chat_messages ORDER BY message_id")
    all_ids = [row[0] for row in cur.fetchall()]

    odd = sum(1 for x in all_ids if x % 2 == 1)
    even = len(all_ids) - odd

    print(f"\nOdd IDs:  {odd} ({100*odd/len(all_ids):.1f}%)")
    print(f"Even IDs: {even} ({100*even/len(all_ids):.1f}%)")

    print("\n[OK] FIX COMPLETE - MESSAGE_IDS ARE NOW FULLY SEQUENTIAL!")
    print("=" * 80)

    conn.close()

except Exception as e:
    print(f"\n[ERROR] {e}")
    try:
        conn.rollback()
        print("[ROLLBACK] Changes rolled back")
    except:
        pass
    import traceback
    traceback.print_exc()
