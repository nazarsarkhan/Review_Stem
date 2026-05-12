from reviewstem.state import extract_changed_files, summarize_diff, summarize_repo_map


SQL_DIFF = """diff --git a/src/db/users.ts b/src/db/users.ts
--- a/src/db/users.ts
+++ b/src/db/users.ts
@@ -1,3 +1,3 @@
-const result = await db.query('SELECT * FROM users WHERE id = $1', [id]);
+const result = await db.query(`SELECT * FROM users WHERE id = ${id}`);
"""

MULTI_FILE_DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-x
+y
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1 @@
-x
+y
"""


def test_extract_changed_files_single():
    assert extract_changed_files(SQL_DIFF) == ["src/db/users.ts"]


def test_extract_changed_files_multiple_dedupes():
    assert extract_changed_files(MULTI_FILE_DIFF) == ["a.py", "b.py"]


def test_extract_changed_files_skips_dev_null():
    deletion = "diff --git a/old.py b/old.py\n--- a/old.py\n+++ /dev/null\n"
    assert extract_changed_files(deletion) == []


def test_summarize_diff_detects_signal_buckets():
    summary = summarize_diff(SQL_DIFF)

    assert "1 changed files" in summary
    assert "database/query" in summary


def test_summarize_repo_map_truncates_long_input():
    big_map = "\n".join(f"file_{i}.py" for i in range(50))

    summary = summarize_repo_map(big_map, max_lines=5)

    assert summary.count("\n") <= 6
    assert "more entries" in summary
