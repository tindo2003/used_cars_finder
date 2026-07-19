"""
A minimal in-memory stand-in for the supabase-py client, shared by the
test suite. Mimics just enough of the fluent query builder
(.select/.insert/.update/.delete/.upsert/.eq/.execute) to exercise
DbClient and the notification matching engine without any network calls.
"""

import itertools

from postgrest.exceptions import APIError

_id_counter = itertools.count(1)


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, table):
        self.table = table
        self.op = None
        self.payload = None
        self.on_conflict = None
        self.filters = {}

    def select(self, *_args):
        self.op = "select"
        return self

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def upsert(self, payload, on_conflict):
        self.op = "upsert"
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def _matching_rows(self):
        return [
            row
            for row in self.table.data
            if all(row.get(k) == v for k, v in self.filters.items())
        ]

    def execute(self):
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
            row = dict(self.payload)
            row.setdefault("id", f"generated-{next(_id_counter)}")
            self.table.data.append(row)
            return FakeResult([row])

        if self.op == "update":
            rows = self._matching_rows()
            for row in rows:
                row.update(self.payload)
            return FakeResult(rows)

        if self.op == "delete":
            rows = self._matching_rows()
            self.table.data = [row for row in self.table.data if row not in rows]
            return FakeResult(rows)

        if self.op == "upsert":
            conflict_columns = self.on_conflict.split(",")
            existing = next(
                (
                    row
                    for row in self.table.data
                    if all(row.get(col) == self.payload.get(col) for col in conflict_columns)
                ),
                None,
            )
            if existing is not None:
                existing.update(self.payload)
                return FakeResult([existing])

            # Real Postgres checks EVERY unique constraint on the table,
            # not just the one named in on_conflict -- original_url has
            # its own separate table-wide uniqueness independent of
            # (vin, dealer_name). Simulate that here so db.py's handling
            # of the cross-dealer-link-collision case is testable.
            if "original_url" not in conflict_columns and self.payload.get("original_url"):
                url_conflict = next(
                    (row for row in self.table.data if row.get("original_url") == self.payload.get("original_url")),
                    None,
                )
                if url_conflict is not None:
                    raise APIError(
                        {
                            "message": (
                                'duplicate key value violates unique constraint '
                                '"listings_original_url_key"'
                            ),
                            "code": "23505",
                            "hint": None,
                            "details": f"Key (original_url)=({self.payload.get('original_url')}) already exists.",
                        }
                    )

            row = dict(self.payload)
            row.setdefault("id", f"generated-{next(_id_counter)}")
            # Mimics a real created_at default now(): fired fresh on
            # INSERT, at essentially the same moment as any last_seen_at
            # the caller stamped into this same payload.
            row.setdefault("created_at", row.get("last_seen_at"))
            self.table.data.append(row)
            return FakeResult([row])

        raise ValueError(f"Unsupported operation: {self.op}")


class FakeTable:
    def __init__(self, name, data=None):
        self.name = name
        self.data = data if data is not None else []
        self.calls = []

    def select(self, *args):
        return FakeQuery(self).select(*args)

    def insert(self, payload):
        return FakeQuery(self).insert(payload)

    def update(self, payload):
        return FakeQuery(self).update(payload)

    def delete(self):
        return FakeQuery(self).delete()

    def upsert(self, payload, on_conflict):
        return FakeQuery(self).upsert(payload, on_conflict=on_conflict)


class FakeSupabase:
    """
    Pass initial_data={"listings": [...], "saved_searches": [...]} to seed
    tables; unseeded tables start empty.
    """

    def __init__(self, initial_data=None):
        initial_data = initial_data or {}
        self._tables = {name: FakeTable(name, data) for name, data in initial_data.items()}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = FakeTable(name)
        return self._tables[name]
