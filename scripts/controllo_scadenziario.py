"""Esegue il controllo operativo usando Supabase o il backup SQLite offline."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _normalizza_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _connessione_disponibile(url: str) -> bool:
    probe = create_engine(_normalizza_url(url), pool_pre_ping=True)
    try:
        with probe.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        probe.dispose()


def _ultimo_backup_sqlite() -> Path | None:
    local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    state_dir = local_appdata / "ScadenziarioCTUPro"
    candidati = list((state_dir / "backup").glob("scadenziario_*.db"))
    candidati.extend((PROJECT_ROOT / "backup").glob("scadenziario_*.db"))
    fallback = state_dir / "data" / "scadenziario.db"
    if fallback.exists():
        candidati.append(fallback)
    project_db = PROJECT_ROOT / "data" / "scadenziario.db"
    if project_db.exists():
        candidati.append(project_db)
    return max(candidati, key=lambda path: path.stat().st_mtime) if candidati else None


def _sqlite_read_only_url(path: Path) -> str:
    return f"sqlite:///file:{path.resolve().as_posix()}?mode=ro&uri=true"


def _configura_database() -> tuple[str, str | None]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url and os.name == "nt":
        from src.local_credentials import load_database_url

        database_url = load_database_url()

    if database_url and _connessione_disponibile(database_url):
        os.environ["DATABASE_URL"] = _normalizza_url(database_url)
        return "Supabase/PostgreSQL", None

    backup = _ultimo_backup_sqlite()
    if backup is None:
        raise RuntimeError("Supabase non raggiungibile e nessun backup SQLite disponibile.")
    os.environ["DATABASE_URL"] = _sqlite_read_only_url(backup)
    return "SQLite offline", str(backup)


def main() -> int:
    fonte, dettaglio_fonte = _configura_database()

    from src.database import get_session
    from src.monitoraggio import formatta_riepilogo_operativo, genera_voci_monitoraggio

    session = get_session()
    try:
        voci = genera_voci_monitoraggio(session)
        print(formatta_riepilogo_operativo(voci, fonte=fonte))
        if dettaglio_fonte:
            print(f"Backup consultato: {dettaglio_fonte}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
