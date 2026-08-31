"""Backup del database locale."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from shutil import copy2

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import DB_PATH, engine, get_session


def _backup_dir() -> Path:
    return Path(DB_PATH).parent.parent / "backup"


def _export_database(dest: Path) -> None:
    from src.models import Base, Documento, Evento, Incarico, ModificaChat, Pagamento, Sospensione, StoricoTermine, Termine

    models = [Incarico, Termine, Evento, Sospensione, Documento, Pagamento, ModificaChat, StoricoTermine]
    sqlite_engine = create_engine(f"sqlite:///{dest}")
    Base.metadata.create_all(bind=sqlite_engine)
    source = get_session()
    target = sessionmaker(bind=sqlite_engine)()
    try:
        for model in models:
            columns = [column.key for column in model.__mapper__.column_attrs]
            for obj in source.query(model).order_by(model.id).all():
                target.merge(model(**{name: getattr(obj, name) for name in columns}))
        target.commit()
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()
        sqlite_engine.dispose()


def crea_backup_database(motivo: str = "manuale") -> Path | None:
    """Crea una copia SQLite timestamped del database corrente."""
    db_path = Path(DB_PATH)
    if engine.name == "sqlite" and not db_path.exists():
        return None

    safe_motivo = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in motivo)
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"scadenziario_{datetime.now():%Y%m%d_%H%M%S}_{safe_motivo}.db"
    if engine.name == "sqlite":
        copy2(db_path, dest)
    else:
        _export_database(dest)
    return dest


def crea_backup_giornaliero() -> Path | None:
    """Esporta il database al massimo una volta ogni 24 ore."""
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backups = sorted(backup_dir.glob("scadenziario_*_giornaliero.db"), reverse=True)
    if backups:
        ultima_modifica = datetime.fromtimestamp(backups[0].stat().st_mtime)
        if datetime.now() - ultima_modifica < timedelta(hours=24):
            return backups[0]
    return crea_backup_database("giornaliero")
