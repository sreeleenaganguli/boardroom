"""DuckDB connection manager for analytical queries."""

import threading
from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd
from app.config import settings


class DuckDBManager:
    """Thread-safe DuckDB connection manager for analytical workloads."""

    _instance: Optional["DuckDBManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._conn = duckdb.connect(
            settings.DUCKDB_PATH,
            config={
                "memory_limit": settings.DUCKDB_MEMORY_LIMIT,
                "threads": settings.DUCKDB_THREADS,
            },
        )
        self._initialized = True

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        return self._conn

    def execute(self, sql: str, params: Optional[List[Any]] = None) -> duckdb.DuckDBPyRelation:
        """Execute a SQL query and return the relation."""
        if params:
            return self._conn.execute(sql, params)
        return self._conn.execute(sql)

    def query_df(self, sql: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
        """Execute a SQL query and return results as a pandas DataFrame."""
        result = self.execute(sql, params)
        return result.fetchdf()

    def query_dicts(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results as a list of dicts."""
        df = self.query_df(sql, params)
        return df.to_dict(orient="records")

    def query_arrow(self, sql: str, params: Optional[List[Any]] = None):
        """Execute a SQL query and return results as an Arrow table."""
        result = self.execute(sql, params)
        return result.fetch_arrow_table()

    def register_dataframe(self, name: str, df: pd.DataFrame):
        """Register a pandas DataFrame as a virtual table in DuckDB."""
        self._conn.register(name, df)

    def register_csv(self, table_name: str, file_path: str, **kwargs):
        """Create a table from a CSV file."""
        options = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
        opts_str = f", {options}" if options else ""
        sql = f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM read_csv_auto('{file_path}'{opts_str})"
        self._conn.execute(sql)

    def register_parquet(self, table_name: str, file_path: str):
        """Create a table from a Parquet file."""
        sql = f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM read_parquet('{file_path}')"
        self._conn.execute(sql)

    def register_json(self, table_name: str, file_path: str):
        """Create a table from a JSON file."""
        sql = f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM read_json_auto('{file_path}')"
        self._conn.execute(sql)

    def get_table_schema(self, table_name: str) -> List[Dict[str, str]]:
        """Get the schema of a registered table."""
        result = self._conn.execute(f"DESCRIBE \"{table_name}\"").fetchall()
        return [
            {"column_name": row[0], "data_type": row[1], "nullable": row[2] == "YES"}
            for row in result
        ]

    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """Get basic statistics for a table."""
        count = self._conn.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()[0]
        columns = self.get_table_schema(table_name)
        return {
            "row_count": count,
            "column_count": len(columns),
            "columns": columns,
        }

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        try:
            self._conn.execute(f"SELECT 1 FROM \"{table_name}\" LIMIT 0")
            return True
        except duckdb.CatalogException:
            return False

    def drop_table(self, table_name: str):
        """Drop a table if it exists."""
        self._conn.execute(f"DROP TABLE IF EXISTS \"{table_name}\"")

    def list_tables(self) -> List[str]:
        """List all tables in the database."""
        result = self._conn.execute("SHOW TABLES").fetchall()
        return [row[0] for row in result]

    def close(self):
        """Close the DuckDB connection."""
        if self._conn:
            self._conn.close()
            self._initialized = False
            DuckDBManager._instance = None


def get_duckdb() -> DuckDBManager:
    """Get the singleton DuckDB manager instance."""
    return DuckDBManager()
