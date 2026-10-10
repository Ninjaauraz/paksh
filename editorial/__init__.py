"""Paksh editorial layer (Milestone 1: safety foundation).

Isolation contract: this package never imports the pipeline (database, export_static,
analyze, ...), never opens SQLite, and never writes anywhere except where a caller
explicitly passes an output path (nothing in Milestone 1 does). Generated story rows
are only ever READ, as plain dicts handed in by the caller.
"""
