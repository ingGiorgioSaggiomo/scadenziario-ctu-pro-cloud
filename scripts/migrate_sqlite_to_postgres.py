"""Migra i dati dal database SQLite locale a PostgreSQL.

Uso:
    python scripts/migrate_sqlite_to_postgres.py --sqlite data/scadenziario.db

Richiede DATABASE_URL impostato verso PostgreSQL. Per evitare sovrascritture
accidentali, usare --replace solo quando si vuole svuotare il database remoto.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.models import Base, Documento, Evento, Incarico, Sospensione, Termine


MODELS = [Incarico, Termine, Evento, Sospensione, Documento]


def _database_url() -> str:
    supabase_password = os.environ.get("SUPABASE_DB_PASSWORD")
    if supabase_password:
        return (
            "postgresql://postgres.wakhbvofmkwlrujggikg:"
            f"{quote(supabase_password, safe='')}@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
        )

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Imposta SUPABASE_DB_PASSWORD oppure DATABASE_URL prima di migrare.")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url.startswith("postgresql://"):
        raise SystemExit("DATABASE_URL deve puntare a PostgreSQL.")
    return url


def _copy_model(src_session, dst_session, model) -> int:
    columns = [col.key for col in model.__mapper__.column_attrs]
    count = 0
    for obj in src_session.query(model).order_by(model.id).all():
        data = {name: getattr(obj, name) for name in columns}
        dst_session.merge(model(**data))
        count += 1
    return count


def _reset_postgres_sequences(engine) -> None:
    with engine.begin() as conn:
        for model in MODELS:
            table = model.__tablename__
            max_id = conn.execute(text(f"SELECT COALESCE(MAX(id), 1) FROM {table}")).scalar()
            has_rows = conn.execute(text(f"SELECT COUNT(*) > 0 FROM {table}")).scalar()
            conn.execute(text(
                "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), :value, :has_rows)"
            ), {"table_name": table, "value": max_id, "has_rows": has_rows})


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra Scadenziario CTU Pro da SQLite a PostgreSQL.")
    parser.add_argument("--sqlite", default="data/scadenziario.db", help="Percorso del database SQLite sorgente.")
    parser.add_argument("--replace", action="store_true", help="Svuota prima le tabelle PostgreSQL di destinazione.")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"Database SQLite non trovato: {sqlite_path}")

    src_engine = create_engine(f"sqlite:///{sqlite_path}")
    dst_engine = create_engine(_database_url())
    if dst_engine.name != "postgresql":
        raise SystemExit("La destinazione non e' PostgreSQL.")

    Base.metadata.create_all(bind=dst_engine)
    SrcSession = sessionmaker(bind=src_engine)
    DstSession = sessionmaker(bind=dst_engine)

    src_session = SrcSession()
    dst_session = DstSession()
    try:
        if args.replace:
            for model in reversed(MODELS):
                dst_session.query(model).delete()
            dst_session.commit()

        totals = {}
        for model in MODELS:
            totals[model.__tablename__] = _copy_model(src_session, dst_session, model)
        dst_session.commit()
        _reset_postgres_sequences(dst_engine)
    finally:
        src_session.close()
        dst_session.close()

    print("Migrazione completata:")
    for table, count in totals.items():
        print(f"- {table}: {count}")


if __name__ == "__main__":
    main()
