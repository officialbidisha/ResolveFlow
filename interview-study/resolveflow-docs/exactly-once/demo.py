import sys, time, threading, psycopg
from concurrent.futures import ThreadPoolExecutor
from side_effects import SCHEMA, post_once

class FakeGitHub:                       # stand-in: no idempotency keys, just like the real API
    def __init__(self): self.comments, self.lock = [], threading.Lock()
    def post_comment(self, body):
        time.sleep(0.2)                 # widen the race window
        with self.lock: self.comments.append(body)
    def list_comments(self):
        with self.lock: return list(self.comments)

dsn = sys.argv[1]
def conn(): return psycopg.connect(dsn, autocommit=True)
c0 = conn(); c0.execute(SCHEMA); c0.execute("TRUNCATE side_effects")

print("\n1) RACE: 5 pods resume the same thread at once")
gh = FakeGitHub()
def pod(i): return post_once(conn(), gh, "thread-1", "comment", "Automated diagnosis")
with ThreadPoolExecutor(5) as ex: print("   results:", list(ex.map(pod, range(5))))
print(f"   comments on GitHub: {len(gh.comments)}   (naive code would give 5)")

print("\n2) CRASH AFTER POST, BEFORE RECORD, then retry")
gh = FakeGitHub()
try: post_once(conn(), gh, "thread-2", "comment", "Automated diagnosis", crash_after_post=True)
except RuntimeError as e: print("   pod A:", e)
print("   retry immediately  ->", post_once(conn(), gh, "thread-2", "comment", "x", stale_after=300),
      "(claim still fresh: don't steal from a possibly-slow owner)")
print("   retry after stale  ->", post_once(conn(), gh, "thread-2", "comment", "x", stale_after=0),
      "(marker found: adopt, don't repost)")
print(f"   comments on GitHub: {len(gh.comments)}   (without the marker check: 2)")

print("\n3) CRASH BEFORE POST, then retry")
gh = FakeGitHub()
c = conn(); c.execute("INSERT INTO side_effects (thread_id, step, status) VALUES ('thread-3','comment','claimed')")
print("   retry after stale  ->", post_once(conn(), gh, "thread-3", "comment", "Automated diagnosis", stale_after=0))
print(f"   comments on GitHub: {len(gh.comments)}")
print("   retry again        ->", post_once(conn(), gh, "thread-3", "comment", "x", stale_after=0), "(done rows are never retaken)")
