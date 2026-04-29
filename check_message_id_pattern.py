"""
Check message_id pattern more closely
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
except:
    pass

conn = psycopg2.connect(
    host=db_config.get("host"),
    user=db_config.get("user"),
    password=db_config.get("password"),
    database=db_config.get("database"),
    port=int(db_config.get("port", 5432)),
    sslmode=db_config.get("sslmode", "require")
)
cur = conn.cursor()

print("=" * 80)
print("MESSAGE_ID PATTERN ANALYSIS - ALL ROWS")
print("=" * 80)

# Get all message_ids
cur.execute("SELECT message_id, serial_no FROM chat_messages ORDER BY message_id")
rows = cur.fetchall()

msg_ids = [r[0] for r in rows]
serial_nos = [r[1] for r in rows]

# Count odd/even
odd_count = sum(1 for x in msg_ids if x % 2 == 1)
even_count = sum(1 for x in msg_ids if x % 2 == 0)

print(f"\nTotal rows: {len(msg_ids)}")
print(f"Odd message_ids: {odd_count}")
print(f"Even message_ids: {even_count}")
print(f"Ratio: {odd_count}/{len(msg_ids)} = {100*odd_count/len(msg_ids):.1f}%")

# Check for pattern
print(f"\nFirst 30 message_ids: {msg_ids[:30]}")
print(f"Last 30 message_ids: {msg_ids[-30:]}")

# Show gaps
print(f"\nGaps in message_id sequence:")
gaps = []
for i in range(len(msg_ids) - 1):
    if msg_ids[i+1] - msg_ids[i] != 1:
        gap_range = list(range(msg_ids[i]+1, msg_ids[i+1]))
        gaps.append((msg_ids[i], msg_ids[i+1], gap_range))

for start, end, missing in gaps:
    print(f"  Gap: {start} -> {end}")
    print(f"    Missing: {missing}")

# Show rows around gaps
if gaps:
    print(f"\nRows BEFORE and AFTER gaps:")
    for start, end, missing in gaps:
        cur.execute("""
            SELECT message_id, serial_no, user_id, intent_label, memory_used, rag_used
            FROM chat_messages
            WHERE message_id IN (%s, %s)
        """, (start, end))
        rows_around = cur.fetchall()
        print(f"\n  Gap {start}->{end}:")
        for row in rows_around:
            print(f"    {row}")

print("\n" + "=" * 80)

conn.close()
