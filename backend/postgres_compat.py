"""Small compatibility wrapper so existing domain SQL can run on psycopg.

The domain layer uses SQLite-style ``?`` placeholders and accesses rows by
both column name and numeric index. This wrapper keeps that contract while
the storage backend is PostgreSQL.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal


class HybridRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def normalize_value(value, column_name=""):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if column_name.endswith("_json") and isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def translate_sql(query: str) -> str:
    query = query.replace("?", "%s")
    query = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", "%s", query)
    query = re.sub(r"\benabled\s*=\s*1\b", "enabled=TRUE", query, flags=re.IGNORECASE)
    query = re.sub(r"\benabled\s*=\s*0\b", "enabled=FALSE", query, flags=re.IGNORECASE)
    return query


def adapt_params(params):
    if params is None:
        return params
    try:
        from psycopg.types.json import Json
    except ImportError:
        Json = None
    adapted = []
    for value in params:
        if Json and isinstance(value, str) and value[:1] in {"{", "["}:
            try:
                adapted.append(Json(json.loads(value)))
                continue
            except json.JSONDecodeError:
                pass
        adapted.append(value)
    return tuple(adapted)


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=()):
        if isinstance(params, dict):
            names = re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", query)
            params = tuple(params[name] for name in names)
        self._cursor.execute(translate_sql(query), adapt_params(params))
        return self

    def executemany(self, query, params_seq: Iterable):
        prepared = []
        for params in params_seq:
            if isinstance(params, dict):
                names = re.findall(r":([A-Za-z_][A-Za-z0-9_]*)", query)
                params = tuple(params[name] for name in names)
            prepared.append(adapt_params(params))
        self._cursor.executemany(translate_sql(query), prepared)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return None if row is None else HybridRow((column.name, normalize_value(value, column.name)) for column, value in zip(self._cursor.description, row))

    def fetchall(self):
        return [HybridRow((column.name, normalize_value(value, column.name)) for column, value in zip(self._cursor.description, row)) for row in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, query, params=()):
        return PostgresCursor(self._connection.cursor()).execute(query, params)

    def executemany(self, query, params_seq):
        return PostgresCursor(self._connection.cursor()).executemany(query, params_seq)

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()
