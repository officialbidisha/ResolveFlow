SCHEMA = """
CREATE TABLE IF NOT EXISTS side_effects (
    thread_id TEXT,
    step TEXT,
    status TEXT NOT NULL, 
    result JSONB,
    claimed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (thread_id, step)
)"""

def marker(thread_id, step):
    return f"<!-- resolveflow:{thread_id}:{step} -->"

def try_claim(conn, thread_id, step, stale_after):
    row = conn.execute(
        """
        INSERT INTO side_effects (thread_id, step, status)
        VALUES (%s, %s, 'claimed')
        ON CONFLICT (thread_id, step) DO UPDATE SET claimed_at = now()
            WHERE side_effects.status = 'claimed'
                AND side_effects.claimed_at < now() - make_interval(secs => %s)
        RETURNING 1
        """, 
        (thread_id,step, stale_after)
    ).fetchone()
    return row is not None

def post_once(conn, gh, thread_id, step, body, stale_after=300, crash_after_post=False):
    if not try_claim(conn, thread_id, step, stale_after):
        status = conn.execute(
            "SELECT status FROM side_effects WHERE thread_id=%s AND step=%s",
            (thread_id, step),
        ).fetchone()[0]
        return f"skipped({status})"

    m = marker(thread_id, step)
    if any(m in c for c in gh.list_comments()):
        outcome = "adopted"
    else:
        gh.post_comment(f"{body}\n{m}")
        outcome = "posted"

    if crash_after_post:
        raise RuntimeError("simulated crash after GitHub write, before recording")

    conn.execute(
        "UPDATE side_effects SET status='done' WHERE thread_id=%s AND step=%s",
        (thread_id, step),
    )
    return outcome
