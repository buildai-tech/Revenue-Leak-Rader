"""fix_sqlite_timestamp_defaults

Replace the SQLite-incompatible ``now()`` server default on timestamp columns
with ``CURRENT_TIMESTAMP``, which is valid on BOTH SQLite (dev) and
PostgreSQL (prod).

The initial migration (7f42829f8e13) created these columns with
``server_default=sa.text('now()')``. On PostgreSQL ``now()`` is valid, but on
SQLite the literal lands in the table DDL as ``DEFAULT (now())``, so any INSERT
that omits the column fails with:

    sqlite3.OperationalError: unknown function: now()

ORM writes are already safe because every timestamp column now carries a
Python-side default (see app/models/timestamps.py), but this migration repairs
the stored schema so the database itself is portable across both backends.

SQLite cannot ALTER a column DEFAULT in place, so each affected table is
rebuilt: rows are held in a plain holder table (CTAS), the table is recreated
from its EXACT original DDL text with only the default expression swapped,
rows are copied back column-by-column, and indexes are recreated verbatim.
No data is modified or lost, no column type / name is altered, and (unlike
batch ALTER + RENAME) the stored schema text stays byte-identical apart from
the default.

Revision ID: 9c1f4e7a2b5d
Revises: 7f42829f8e13
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9c1f4e7a2b5d'
down_revision: Union[str, None] = '7f42829f8e13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) pairs carrying a server-side timestamp default.
TIMESTAMP_COLUMNS: list[tuple[str, str]] = [
    ("audit_log", "created_at"),
    ("background_jobs", "created_at"),
    ("column_mappings", "created_at"),
    ("data_imports", "created_at"),
    ("financial_calculations", "calculated_at"),
    ("identity_merge_log", "created_at"),
    ("interventions", "created_at"),
    ("interventions", "updated_at"),
    ("lead_events", "created_at"),
    ("leads", "created_at"),
    ("leakage_evidence", "created_at"),
    ("leakage_events", "created_at"),
    ("organizations", "created_at"),
    ("projects", "created_at"),
    ("recommendations", "created_at"),
    ("sales_reps", "created_at"),
]

BROKEN_DEFAULT = "DEFAULT (now())"
FIXED_DEFAULT = "DEFAULT CURRENT_TIMESTAMP"


def _sqlite_rebuild_table(
    bind, table_name: str, from_default: str, to_default: str
) -> None:
    """Rebuild *table_name* with its EXACT existing DDL, swapping
    *from_default* for *to_default*. All rows, foreign keys and indexes are
    preserved, and the stored schema text changes by nothing except the default
    expression. Idempotent: tables not containing *from_default* are skipped."""
    ddl = bind.execute(
        sa.text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = :name"
        ),
        {"name": table_name},
    ).scalar()

    if ddl is None or from_default not in ddl:
        return  # table absent, or default already correct

    shadow = f"__mig_hold_{table_name}"

    # 0. Clean up any holder table left over by an interrupted run.
    bind.execute(sa.text(f'DROP TABLE IF EXISTS "{shadow}"'))

    # 1. Stash the index DDLs (they are dropped together with the old table).
    index_ddls = [
        r[0]
        for r in bind.execute(
            sa.text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = :name AND sql IS NOT NULL"
            ),
            {"name": table_name},
        ).fetchall()
    ]

    # 2. Hold every row in a plain (untyped) holder table — values only.
    bind.execute(
        sa.text(f'CREATE TABLE "{shadow}" AS SELECT * FROM "{table_name}"')
    )

    # 3. Drop the original and recreate it from its EXACT original DDL text
    #    with only the default expression swapped (avoids ALTER TABLE RENAME,
    #    which would rewrite the stored schema text with a quoted name).
    bind.execute(sa.text("PRAGMA foreign_keys = OFF"))
    bind.execute(sa.text(f'DROP TABLE "{table_name}"'))
    bind.execute(sa.text(ddl.replace(from_default, to_default)))

    # 4. Copy the rows back, column by explicit column (order is identical).
    columns = [
        r[1]
        for r in bind.execute(sa.text(f'PRAGMA table_info("{table_name}")')).fetchall()
    ]
    collist = ", ".join(f'"{c}"' for c in columns)
    bind.execute(
        sa.text(
            f'INSERT INTO "{table_name}" ({collist}) '
            f'SELECT {collist} FROM "{shadow}"'
        )
    )

    # 5. Drop the holder and recreate the indexes verbatim.
    bind.execute(sa.text(f'DROP TABLE "{shadow}"'))
    for idx_sql in index_ddls:
        bind.execute(sa.text(idx_sql))


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        for table_name, _column_name in TIMESTAMP_COLUMNS:
            _sqlite_rebuild_table(bind, table_name, BROKEN_DEFAULT, FIXED_DEFAULT)
    elif bind.dialect.name == "postgresql":
        # ``now()`` is valid on PostgreSQL (and matches func.now() there);
        # normalize the default explicitly — no table rewrite needed.
        for table_name, column_name in TIMESTAMP_COLUMNS:
            op.execute(
                f'ALTER TABLE {table_name} ALTER COLUMN {column_name} SET DEFAULT now()'
            )
    else:
        raise NotImplementedError(
            f"Dialect '{bind.dialect.name}' is not supported by this migration."
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        # Faithfully restore the previous (broken-on-SQLite) default.
        for table_name, _column_name in TIMESTAMP_COLUMNS:
            _sqlite_rebuild_table(bind, table_name, FIXED_DEFAULT, BROKEN_DEFAULT)
    elif bind.dialect.name == "postgresql":
        # ``now()`` was the pre-existing default on PostgreSQL — nothing to do.
        pass
