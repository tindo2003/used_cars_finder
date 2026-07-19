"""
A minimal in-memory stand-in for the supabase-py client, shared by the
test suite. Mimics just enough of the fluent query builder
(.select/.insert/.update/.delete/.upsert/.eq/.execute) to exercise
DbClient and the notification matching engine without any network calls.
"""

import itertools
from typing import Any, Dict, List, Optional

_id_counter = itertools.count(1)


class FakeResult:
    def __init__(self, data: List[Dict[str, Any]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, table: "FakeTable") -> None:
        self.table = table
        self.op: Optional[str] = None
        self.payload: Optional[Dict[str, Any]] = None
        self.on_conflict: Optional[str] = None
        self.filters: Dict[str, Any] = {}

    def select(self, *_args: Any) -> "FakeQuery":
        self.op = "select"
        return self

    def insert(self, payload: Dict[str, Any]) -> "FakeQuery":
        self.op = "insert"
        self.payload = payload
        return self

    def update(self, payload: Dict[str, Any]) -> "FakeQuery":
        self.op = "update"
        self.payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self.op = "delete"
        return self

    def upsert(self, payload: Dict[str, Any], on_conflict: str) -> "FakeQuery":
        self.op = "upsert"
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def eq(self, key: str, value: Any) -> "FakeQuery":
        self.filters[key] = value
        return self

    def _matching_rows(self) -> List[Dict[str, Any]]:
        return [
            row
            for row in self.table.data
            if all(row.get(k) == v for k, v in self.filters.items())
        ]

    def execute(self) -> FakeResult:
        self.table.calls.append(
            {
                "op": self.op,
                "payload": self.payload,
                "on_conflict": self.on_conflict,
                "filters": dict(self.filters),
            }
        )

        if self.op == "select":
            return FakeResult(self._matching_rows())

        if self.op == "insert":
            assert self.payload is not None
            row = dict(self.payload)
            row.setdefault("id", f"generated-{next(_id_counter)}")
            self.table.data.append(row)
            return FakeResult([row])

        if self.op == "update":
            assert self.payload is not None
            rows = self._matching_rows()
            for row in rows:
                row.update(self.payload)
            return FakeResult(rows)

        if self.op == "delete":
            rows = self._matching_rows()
            self.table.data = [row for row in self.table.data if row not in rows]
            return FakeResult(rows)

        if self.op == "upsert":
            assert self.payload is not None
            assert self.on_conflict is not None
            payload = self.payload
            conflict_columns = self.on_conflict.split(",")
            existing = next(
                (
                    row
                    for row in self.table.data
                    if all(row.get(col) == payload.get(col) for col in conflict_columns)
                ),
                None,
            )
            if existing is not None:
                existing.update(payload)
                return FakeResult([existing])

            row = dict(payload)
            row.setdefault("id", f"generated-{next(_id_counter)}")
            # Mimics a real created_at default now(): fired fresh on
            # INSERT, at essentially the same moment as any last_seen_at
            # the caller stamped into this same payload.
            row.setdefault("created_at", row.get("last_seen_at"))
            self.table.data.append(row)
            return FakeResult([row])

        raise ValueError(f"Unsupported operation: {self.op}")


class FakeTable:
    def __init__(self, name: str, data: Optional[List[Dict[str, Any]]] = None) -> None:
        self.name = name
        self.data: List[Dict[str, Any]] = data if data is not None else []
        self.calls: List[Dict[str, Any]] = []

    def select(self, *args: Any) -> FakeQuery:
        return FakeQuery(self).select(*args)

    def insert(self, payload: Dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).insert(payload)

    def update(self, payload: Dict[str, Any]) -> FakeQuery:
        return FakeQuery(self).update(payload)

    def delete(self) -> FakeQuery:
        return FakeQuery(self).delete()

    def upsert(self, payload: Dict[str, Any], on_conflict: str) -> FakeQuery:
        return FakeQuery(self).upsert(payload, on_conflict=on_conflict)


class FakeSupabase:
    """
    Pass initial_data={"listings": [...], "saved_searches": [...]} to seed
    tables; unseeded tables start empty.
    """

    def __init__(self, initial_data: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> None:
        initial_data = initial_data or {}
        self._tables = {name: FakeTable(name, data) for name, data in initial_data.items()}

    def table(self, name: str) -> FakeTable:
        if name not in self._tables:
            self._tables[name] = FakeTable(name)
        return self._tables[name]
