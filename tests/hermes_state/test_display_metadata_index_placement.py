"""Placement of the covering index on ``messages.display_metadata``.

``idx_messages_display_metadata`` is a *covering* index: the read that wants it
(``SELECT display_metadata FROM messages WHERE display_metadata LIKE
'%reactions%'``) cannot seek on a leading-wildcard LIKE, but because the query
touches only ``display_metadata`` SQLite can answer it from the index without
visiting a single table page — ``SCAN messages USING COVERING INDEX
idx_messages_display_metadata``. On a multi-GB ``state.db`` that is the
difference between a cold full scan of ``messages`` and an index scan over
roughly 1/500th of the file.

Where that statement lives is load-bearing, not cosmetic. ``display_metadata``
arrived with the ``display_*`` wave, so a legacy store does not have the
column, and ``CREATE TABLE IF NOT EXISTS messages`` in ``SCHEMA_SQL`` cannot
add it. ``_reconcile_columns()`` does — but only *after*
``cursor.executescript(SCHEMA_SQL)`` has already run: ``_init_schema`` does
``executescript(SCHEMA_SQL)`` → ``_reconcile_columns()`` →
``_execute_ddl_skipping_settled_triggers(cursor, DEFERRED_INDEX_SQL)``. An
index over the column placed in ``SCHEMA_SQL`` therefore aborts the whole
``executescript`` (``no such column: display_metadata``): the store does not
open at all, on exactly the legacy stores the reconciler exists for.

Mutation check: moving the statement from ``DEFERRED_INDEX_SQL`` into
``SCHEMA_SQL`` (the same two lines, no other change) fails
``test_legacy_store_without_display_metadata_opens`` here with
``sqlite3.OperationalError: no such column: display_metadata``.
"""

from __future__ import annotations

import sqlite3

from hermes_state import SessionDB

INDEX = "idx_messages_display_metadata"


def _index_exists(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (INDEX,),
        ).fetchone()
        is not None
    )


def _make_legacy_store(path) -> None:
    """Turn a fresh store into the pre-``display_*``-wave shape.

    Drops the index first: SQLite refuses ``ALTER TABLE … DROP COLUMN`` while
    an index names the column.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"DROP INDEX IF EXISTS {INDEX}")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        assert "display_metadata" in columns, "fresh store must have the column"
        conn.execute("ALTER TABLE messages DROP COLUMN display_metadata")
        conn.commit()
    finally:
        conn.close()


def test_legacy_store_without_display_metadata_opens(tmp_path):
    """An index in SCHEMA_SQL over a reconciler-added column kills the open."""
    path = tmp_path / "legacy.db"
    SessionDB(path).close()
    _make_legacy_store(path)

    reopened = SessionDB(path)  # must not raise
    try:
        conn = reopened._conn
        assert conn is not None
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        assert "display_metadata" in columns, (
            "_reconcile_columns must re-add display_metadata on a legacy store"
        )
        assert _index_exists(conn), (
            f"{INDEX} must exist once the legacy store has been opened"
        )
    finally:
        reopened.close()


def test_fresh_store_gets_the_index(tmp_path):
    db = SessionDB(tmp_path / "state.db")
    try:
        conn = db._conn
        assert conn is not None
        assert _index_exists(conn)
    finally:
        db.close()
