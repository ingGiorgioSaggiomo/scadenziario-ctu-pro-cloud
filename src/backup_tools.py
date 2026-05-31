"""Backup del database locale."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from shutil import copy2

from src.database import DB_PATH


def crea_backup_database(motivo: str = "manuale") -> Path | None:
    """Crea una copia timestamped del database, se presente."""
    db_path = Path(DB_PATH)
    if not db_path.exists():
        return None

    safe_motivo = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in motivo)
    backup_dir = db_path.parent.parent / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"scadenziario_{datetime.now():%Y%m%d_%H%M%S}_{safe_motivo}.db"
    copy2(db_path, dest)
    return dest
