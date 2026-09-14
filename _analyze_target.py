"""Analyze SQLite v2 msg_count distribution and subagent patterns."""
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from kiro_history import _load_sqlite_sessions

sessions = _load_sqlite_sessions()
v2 = [s for s in sessions if s.get("source") == "sqlite_v2"]

print(f"Total SQLite v2 sessions: {len(v2)}\n")

# Distribution of msg_count
dist = Counter(s["msg_count"] for s in v2)
print("msg_count distribution:")
for k in sorted(dist):
    print(f"  {k:3d} msgs: {dist[k]:4d} sessions")

print()

# is_subagent=True with msg_count > 1
multi_subagent = [s for s in v2 if s.get("is_subagent") and s["msg_count"] > 1]
print(f"is_subagent=True AND msg_count > 1: {len(multi_subagent)}")
for s in multi_subagent[:5]:
    print(f"  {s['session_id'][:8]}... msg_count={s['msg_count']} title={s.get('title','')[:50]}")

print()

# msg_count==1, is_subagent=False (the suspicious ones)
suspicious = [s for s in v2 if s["msg_count"] == 1 and not s.get("is_subagent")]
print(f"msg_count==1 AND is_subagent=False: {len(suspicious)} sessions")
print("(These WOULD be filtered by msg_count<=1 rule)")
for s in suspicious[:10]:
    print(f"  {s['session_id'][:8]}... title={s.get('title','')[:60]}")
