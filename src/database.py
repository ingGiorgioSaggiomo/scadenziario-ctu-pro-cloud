import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session

def _resolve_db_path() -> Path:
    if getattr(sys, "frozen", False):
        local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return local_appdata / "ScadenziarioCTUPro" / "data" / "scadenziario.db"
    return Path(__file__).resolve().parent.parent / "data" / "scadenziario.db"


DB_PATH = _resolve_db_path()

def _get_database_url() -> str:
    # 1. Controlla variabili d'ambiente (universale)
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # 2. Controlla secrets di Streamlit
    try:
        import streamlit as st
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
        elif "connections" in st.secrets and "postgresql" in st.secrets["connections"]:
            return st.secrets["connections"]["postgresql"].get("url")
    except Exception:
        pass

    # 3. Fallback locale
    return f"sqlite:///{DB_PATH}"


DB_URL = _get_database_url()
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DB_URL, echo=False)

SessionLocal = sessionmaker(bind=engine)


def get_session() -> Session:
    return SessionLocal()


def init_db():
    from src.models import Base
    if engine.name == "sqlite":
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Migrazione leggera: aggiunge colonne mancanti e adatta vincoli."""
    expected = {
        "incarichi": [
            ("data_inizio_operazioni", "DATE"),
            ("data_invio_bozza", "DATE"),
            ("data_ricezione_osservazioni", "DATE"),
            ("priorita", "VARCHAR(20) DEFAULT 'media'"),
            ("origine_dato", "VARCHAR(20) DEFAULT 'manuale'"),
        ],
        "sospensioni": [
            ("incide_su_scadenze", "BOOLEAN DEFAULT true"),
        ],
        "eventi": [
            ("completato", "BOOLEAN DEFAULT false"),
            ("annullato", "BOOLEAN DEFAULT false"),
        ],
    }

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table, cols in expected.items():
            if table not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspect(engine).get_columns(table)}
            for col_name, col_def in cols:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))

    _ensure_eventi_data_nullable()


def _ensure_eventi_data_nullable():
    """Rende nullable la colonna eventi.data per DB con schema vecchio."""
    from src.models import Base
    inspector = inspect(engine)
    if "eventi" not in inspector.get_table_names():
        return
    cols = inspector.get_columns("eventi")
    data_col = next((c for c in cols if c["name"] == "data"), None)
    if data_col is None or data_col.get("nullable", True):
        return

    old_col_names = [c["name"] for c in cols]
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE eventi RENAME TO _eventi_old"))
    Base.metadata.tables["eventi"].create(bind=engine)
    with engine.begin() as conn:
        col_list = ", ".join(old_col_names)
        conn.execute(text(
            f"INSERT INTO eventi ({col_list}) SELECT {col_list} FROM _eventi_old"
        ))
        conn.execute(text("DROP TABLE _eventi_old"))


def elimina_dati_demo(session) -> int:
    """Elimina tutti gli incarichi (e cascata) con origine_dato='demo'.

    Restituisce il numero di incarichi eliminati.
    """
    from src.models import Incarico
    incs = session.query(Incarico).filter(Incarico.origine_dato == "demo").all()
    n = len(incs)
    for inc in incs:
        session.delete(inc)
    session.commit()
    return n


def elimina_incarico(session, incarico_id: int) -> bool:
    """Elimina un incarico per id, inclusi i dati collegati via cascade."""
    from src.models import Incarico

    incarico = session.get(Incarico, incarico_id)
    if incarico is None:
        return False

    session.delete(incarico)
    session.commit()
    return True
