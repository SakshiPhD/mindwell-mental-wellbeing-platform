"""
Comprehensive database diagnostic to check for issues and understand sequence patterns.
"""
import streamlit as st
import psycopg2
from psycopg2 import extensions

# Get connection from Streamlit secrets
@st.cache_resource
def get_db_connection():
    """Get cached database connection."""
    try:
        conn = psycopg2.connect(
            host=st.secrets["database"]["host"],
            user=st.secrets["database"]["user"],
            password=st.secrets["database"]["password"],
            database=st.secrets["database"]["database"],
            sslmode="require"
        )
        return conn
    except Exception as e:
        st.error(f"Connection failed: {e}")
        return None

def run_diagnostic():
    """Run comprehensive database diagnostic."""
    conn = get_db_connection()
    if not conn:
        st.error("Cannot connect to database")
        return

    cur = conn.cursor()

    st.title("🔍 Database Diagnostic Report")

    # ==================== 1. CHECK SEQUENCES ====================
    st.header("1. Sequences Analysis")

    cur.execute("""
        SELECT sequence_name, last_value, increment_by, start_value
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
        ORDER BY sequence_name
    """)
    sequences = cur.fetchall()

    st.subheader("All Database Sequences")
    for seq_name, last_val, incr_by, start_val in sequences:
        col1, col2, col3, col4 = st.columns(4)
        col1.write(f"**{seq_name}**")
        col2.write(f"Last: {last_val}")
        col3.write(f"Incr: {incr_by}")
        col4.write(f"Start: {start_val}")

    # ==================== 2. CHECK CHAT_MESSAGES TABLE ====================
    st.header("2. chat_messages Table Analysis")

    # Get table info
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'chat_messages'
        ORDER BY ordinal_position
    """)
    columns = cur.fetchall()

    st.subheader("Table Schema")
    for col_name, data_type, is_nullable in columns:
        st.write(f"- `{col_name}`: {data_type} (nullable: {is_nullable})")

    # Get row count
    cur.execute("SELECT COUNT(*) FROM chat_messages")
    total_rows = cur.fetchone()[0]
    st.write(f"**Total rows**: {total_rows}")

    # Check for gaps in message_id
    st.subheader("Message ID Pattern Analysis")
    cur.execute("""
        SELECT message_id, serial_no
        FROM chat_messages
        ORDER BY message_id
        LIMIT 50
    """)
    rows = cur.fetchall()

    if rows:
        st.write("First 50 rows:")
        msg_ids = [r[0] for r in rows]
        serial_nos = [r[1] for r in rows]

        col1, col2 = st.columns(2)

        with col1:
            st.write("**message_id values:**")
            st.write(str(msg_ids[:20]))

            # Check if all odd
            is_all_odd = all(mid % 2 == 1 for mid in msg_ids)
            is_all_even = all(mid % 2 == 0 for mid in msg_ids)

            if is_all_odd:
                st.error("❌ ALL message_ids are ODD (sequence increment by 2?)")
            elif is_all_even:
                st.error("❌ ALL message_ids are EVEN (sequence increment by 2?)")
            else:
                st.success("✅ message_ids are sequential (normal)")

        with col2:
            st.write("**serial_no values:**")
            st.write(str(serial_nos[:20]))

            # Check if sequential
            is_sequential = all(serial_nos[i] == i + 1 for i in range(len(serial_nos)))
            if is_sequential:
                st.success("✅ serial_nos are properly sequential (1, 2, 3, ...)")
            else:
                st.warning("⚠️ serial_nos have gaps or issues")

        # Check for gaps
        st.subheader("Gap Detection")
        gaps = []
        for i in range(len(msg_ids) - 1):
            if msg_ids[i+1] - msg_ids[i] != 1:
                gaps.append((msg_ids[i], msg_ids[i+1]))

        if gaps:
            st.error(f"❌ Found {len(gaps)} gaps in message_id sequence:")
            for before, after in gaps[:10]:
                st.write(f"  Gap: {before} → {after} (skipped {after - before - 1})")
        else:
            st.success("✅ No gaps in message_id sequence")

    # ==================== 3. CHECK CHAT_ANALYSIS TABLE ====================
    st.header("3. chat_analysis Table Analysis")

    # Check for visible_serial_no vs serial_no
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'chat_analysis'
        ORDER BY ordinal_position
    """)
    analysis_cols = [col[0] for col in cur.fetchall()]

    st.subheader("Columns in chat_analysis")
    has_visible = "visible_serial_no" in analysis_cols
    has_serial = "serial_no" in analysis_cols

    if has_visible:
        st.error(f"❌ Column 'visible_serial_no' exists (should be renamed to 'serial_no')")
    if has_serial:
        st.success(f"✅ Column 'serial_no' exists")

    if not has_serial and not has_visible:
        st.error("❌ Neither 'serial_no' nor 'visible_serial_no' found!")

    st.write(f"**All columns**: {', '.join(analysis_cols)}")

    # ==================== 4. CHECK OTHER TABLES ====================
    st.header("4. All Tables in Database")

    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [t[0] for t in cur.fetchall()]

    col1, col2, col3 = st.columns(3)
    for i, table in enumerate(tables):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]

        if i % 3 == 0:
            col1.write(f"**{table}**: {count} rows")
        elif i % 3 == 1:
            col2.write(f"**{table}**: {count} rows")
        else:
            col3.write(f"**{table}**: {count} rows")

    # ==================== 5. SQL COMMANDS TO FIX ====================
    st.header("5. SQL Fix Commands")

    st.subheader("A. Reset message_id sequence (if incrementing by 2)")
    st.code("""
-- Get current max message_id
SELECT MAX(message_id) FROM chat_messages;

-- Reset sequence to start from max + 1, incrementing by 1
SELECT setval('chat_messages_message_id_seq',
    COALESCE((SELECT MAX(message_id) FROM chat_messages), 0) + 1);

-- Verify it worked
SELECT nextval('chat_messages_message_id_seq');
SELECT nextval('chat_messages_message_id_seq');
SELECT nextval('chat_messages_message_id_seq');
    """, language="sql")

    st.subheader("B. Rename visible_serial_no to serial_no (if needed)")
    if has_visible and not has_serial:
        st.code("""
ALTER TABLE chat_analysis RENAME COLUMN visible_serial_no TO serial_no;
        """, language="sql")

    st.subheader("C. Fix gaps in message_id (renumber sequentially)")
    st.code("""
-- Create temp table with renumbered IDs
WITH renumbered AS (
    SELECT message_id,
           ROW_NUMBER() OVER (ORDER BY message_id) as new_id
    FROM chat_messages
)
UPDATE chat_messages cm
SET message_id = r.new_id
FROM renumbered r
WHERE cm.message_id = r.message_id;

-- Reset sequence after renumbering
SELECT setval('chat_messages_message_id_seq',
    (SELECT MAX(message_id) FROM chat_messages) + 1);
    """, language="sql")

    # ==================== 6. DETAILED ROW INSPECTION ====================
    st.header("6. Detailed Row Inspection (Last 20 messages)")

    cur.execute("""
        SELECT message_id, serial_no, user_id, intent_label, risk_level,
               memory_used, rag_used, retrieved_count
        FROM chat_messages
        ORDER BY message_id DESC
        LIMIT 20
    """)
    detailed_rows = cur.fetchall()

    import pandas as pd
    if detailed_rows:
        df = pd.DataFrame(detailed_rows, columns=[
            "message_id", "serial_no", "user_id", "intent_label", "risk_level",
            "memory_used", "rag_used", "retrieved_count"
        ])
        st.dataframe(df, use_container_width=True)

    conn.close()

if __name__ == "__main__":
    run_diagnostic()
