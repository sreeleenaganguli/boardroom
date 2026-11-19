"""SQL sandboxing using sqlglot to validate and restrict SQL queries."""

from typing import List, Optional, Set
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError


class SQLSandboxError(Exception):
    """Raised when a SQL query violates sandbox rules."""
    pass


# Dangerous SQL operations that should be blocked
BLOCKED_STATEMENTS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
    "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL", "MERGE", "REPLACE",
    "LOAD", "COPY", "ATTACH", "DETACH", "PRAGMA",
}

# Dangerous functions
BLOCKED_FUNCTIONS = {
    "read_csv", "read_parquet", "read_json", "read_csv_auto",
    "httpfs_get", "httpfs_put",
    "copy_to", "export_database",
    "install", "load",
}


def validate_sql(sql: str, allowed_tables: Optional[Set[str]] = None) -> str:
    """Validate and sanitize a SQL query for safe execution.

    Args:
        sql: The SQL query to validate
        allowed_tables: Optional set of table names the query is allowed to access

    Returns:
        The validated SQL string

    Raises:
        SQLSandboxError: If the query violates sandbox rules
    """
    if not sql or not sql.strip():
        raise SQLSandboxError("Empty SQL query")

    try:
        parsed = sqlglot.parse(sql, dialect="duckdb")
    except ParseError as e:
        raise SQLSandboxError(f"SQL parse error: {e}")

    if not parsed:
        raise SQLSandboxError("Failed to parse SQL query")

    for statement in parsed:
        if statement is None:
            continue

        # Check statement type
        stmt_type = type(statement).__name__.upper()
        for blocked in BLOCKED_STATEMENTS:
            if blocked in stmt_type:
                raise SQLSandboxError(
                    f"Blocked SQL operation: {blocked}. Only SELECT queries are allowed."
                )

        # Ensure it's a SELECT statement
        if not isinstance(statement, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
            # Allow WITH (CTE) statements that contain SELECTs
            if isinstance(statement, exp.CTE):
                continue
            # Check if it's a command
            if hasattr(statement, 'key') and statement.key.upper() in BLOCKED_STATEMENTS:
                raise SQLSandboxError(
                    f"Only SELECT queries are allowed. Got: {statement.key}"
                )

        # Check for blocked functions
        for func in statement.find_all(exp.Anonymous, exp.Func):
            func_name = ""
            if isinstance(func, exp.Anonymous):
                func_name = func.name.lower()
            elif hasattr(func, "sql_name"):
                func_name = func.sql_name().lower()
            elif hasattr(func, "key"):
                func_name = func.key.lower()

            if func_name in BLOCKED_FUNCTIONS:
                raise SQLSandboxError(f"Blocked function: {func_name}")

        # Check table access if allowed_tables specified
        if allowed_tables is not None:
            for table in statement.find_all(exp.Table):
                table_name = table.name.lower()
                if table_name and table_name not in {t.lower() for t in allowed_tables}:
                    raise SQLSandboxError(
                        f"Access denied to table: {table_name}. "
                        f"Allowed tables: {', '.join(sorted(allowed_tables))}"
                    )

    # Return the validated SQL
    return sql.strip().rstrip(";")


def extract_tables(sql: str) -> List[str]:
    """Extract table names referenced in a SQL query."""
    try:
        parsed = sqlglot.parse(sql, dialect="duckdb")
    except ParseError:
        return []

    tables = []
    for statement in parsed:
        if statement is None:
            continue
        for table in statement.find_all(exp.Table):
            if table.name:
                tables.append(table.name)
    return list(set(tables))


def add_limit(sql: str, max_rows: int = 10000) -> str:
    """Add a LIMIT clause to a SQL query if it doesn't have one."""
    try:
        parsed = sqlglot.parse(sql, dialect="duckdb")
    except ParseError:
        return sql

    for statement in parsed:
        if statement is None:
            continue
        if isinstance(statement, exp.Select):
            # Check if LIMIT already exists
            if statement.args.get("limit") is None:
                statement = statement.limit(max_rows)
            return statement.sql(dialect="duckdb")

    return sql
