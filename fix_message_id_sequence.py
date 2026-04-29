"""
Fix message_id sequence incrementing issue
Changes INCREMENT BY 2 back to INCREMENT BY 1
"""
import psycopg2

# Load database config
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
    print("FIXING MESSAGE_ID SEQUENCE ISSUE")
    print("=" * 80)

    # Connect to database
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
    print("\n[STEP 1] Checking current sequence state...")
    cur.execute("""
        SELECT sequencename, last_value, increment_by
        FROM pg_sequences
        WHERE sequencename = 'chat_messages_message_id_seq'
    """)
    result = cur.fetchone()

    if result:
        seq_name, last_val, incr_by = result
        print(f"  Sequence: {seq_name}")
        print(f"  Last value: {last_val}")
        print(f"  Increment: {incr_by}")

        if incr_by == 2:
            print(f"  Status: [ERROR] Increment is 2 (should be 1)")
        else:
            print(f"  Status: [OK] Increment is already 1")
    else:
        print("  [ERROR] Sequence not found!")
        conn.close()
        exit(1)

    # Step 2: Alter sequence to increment by 1
    print("\n[STEP 2] Altering sequence to INCREMENT BY 1...")
    cur.execute("ALTER SEQUENCE chat_messages_message_id_seq INCREMENT BY 1")
    print("  [OK] Sequence altered successfully")

    # Step 3: Reset the sequence value
    print("\n[STEP 3] Resetting sequence value to 1246...")
    cur.execute("""
        SELECT setval('chat_messages_message_id_seq', 1246)
    """)
    result = cur.fetchone()
    print(f"  [OK] setval returned: {result[0]}")

    # Step 4: Verify the fix
    print("\n[STEP 4] Verifying the fix...")

    # Get next 5 values (but don't actually insert)
    test_values = []
    for i in range(5):
        cur.execute("SELECT nextval('chat_messages_message_id_seq')")
        val = cur.fetchone()[0]
        test_values.append(val)

    print(f"  Next 5 values would be: {test_values}")

    # Check if they're sequential
    is_sequential = all(test_values[i] == 1246 + i for i in range(len(test_values)))

    if is_sequential:
        print(f"  [OK] Values are sequential: 1246, 1247, 1248, 1249, 1250")
        print(f"  Status: FIX SUCCESSFUL!")
    else:
        print(f"  [ERROR] Values are NOT sequential: {test_values}")
        print(f"  Status: FIX FAILED!")

    # Step 5: Reset sequence to what it should be (undo the test)
    print("\n[STEP 5] Resetting sequence back to 1246 (undoing test calls)...")
    cur.execute("""
        SELECT setval('chat_messages_message_id_seq', 1246)
    """)
    print("  [OK] Sequence reset to 1246")

    # Step 6: Final verification
    print("\n[STEP 6] Final verification...")
    cur.execute("""
        SELECT sequencename, last_value, increment_by
        FROM pg_sequences
        WHERE sequencename = 'chat_messages_message_id_seq'
    """)
    final_result = cur.fetchone()
    seq_name, last_val, incr_by = final_result

    print(f"  Sequence: {seq_name}")
    print(f"  Last value: {last_val}")
    print(f"  Increment: {incr_by}")

    if incr_by == 1:
        print(f"  [OK] INCREMENT BY 1 - FIX COMPLETE!")
    else:
        print(f"  [ERROR] INCREMENT is still {incr_by}")

    # Commit changes
    conn.commit()
    print("\n[COMMIT] Changes committed to database")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("[+] Sequence INCREMENT set to 1")
    print("[+] Sequence value reset to 1246")
    print("[+] Next message_id will be: 1247")
    print("[+] Then: 1248, 1249, 1250... (sequential, no gaps)")
    print("=" * 80)

    conn.close()

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
