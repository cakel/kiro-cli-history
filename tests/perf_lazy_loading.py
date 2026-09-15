"""Measure lazy loading performance improvement."""
import sys
import time
sys.path.insert(0, r'D:\Work\kiro-cli-history')

from session_store import get_sessions, extract_messages
from rich.text import Text
from rich.markdown import Markdown

sessions = get_sessions()
print(f"Total sessions: {len(sessions)}")

# Find sessions with most messages
big_sessions = [(s, s.get('msg_count', 0)) for s in sessions]
big_sessions.sort(key=lambda x: x[1], reverse=True)
print("Top 5 sessions by message count:")
for s, c in big_sessions[:5]:
    title = s.get("title", "?")[:40]
    print(f"  {c} msgs: {title}")

# Test with largest session
test_session = big_sessions[0][0]
msg_count = test_session.get("msg_count", 0)
print(f"\nTesting with session: {msg_count} messages")

# 1. BEFORE: Extract ALL messages (old behavior)
start = time.perf_counter()
all_msgs = extract_messages(test_session)
extract_all_time = time.perf_counter() - start
print(f"\n=== BEFORE (full load) ===")
print(f"1. Extract all {len(all_msgs)} messages: {extract_all_time*1000:.1f}ms")

# Full render simulation
start = time.perf_counter()
for msg in all_msgs:
    if msg['role'] == 'kiro':
        try:
            Markdown(msg['text'])
        except:
            Text(msg['text'])
    else:
        Text(msg['text'])
render_all_time = time.perf_counter() - start
print(f"2. Render all {len(all_msgs)} messages: {render_all_time*1000:.1f}ms")
full_time = extract_all_time + render_all_time
print(f"Total (extract+render all): {full_time*1000:.1f}ms")

# 2. AFTER: Extract only first 30 messages (new behavior)
print(f"\n=== AFTER (lazy load, limit=30) ===")
start = time.perf_counter()
first_30 = extract_messages(test_session, limit=30)
extract_30_time = time.perf_counter() - start
print(f"1. Extract first 30 messages: {extract_30_time*1000:.1f}ms")

# Render first 30
start = time.perf_counter()
for msg in first_30:
    if msg['role'] == 'kiro':
        try:
            Markdown(msg['text'])
        except:
            Text(msg['text'])
    else:
        Text(msg['text'])
render_30_time = time.perf_counter() - start
print(f"2. Render first 30 messages: {render_30_time*1000:.1f}ms")
lazy_time = extract_30_time + render_30_time
print(f"Total (extract+render 30): {lazy_time*1000:.1f}ms")

# Calculate improvement
print(f"\n=== PERFORMANCE IMPROVEMENT ===")
print(f"Before: {full_time*1000:.0f}ms")
print(f"After:  {lazy_time*1000:.0f}ms")
if lazy_time > 0:
    speedup = full_time / lazy_time
    print(f"Speedup: {speedup:.1f}x faster initial display")
    improvement_pct = (1 - lazy_time/full_time) * 100
    print(f"Improvement: {improvement_pct:.0f}% faster")
