"""Test per backup database."""

from pathlib import Path

from src.backup_tools import crea_backup_database


def test_crea_backup_database(tmp_path, monkeypatch):
    db = tmp_path / "data" / "scadenziario.db"
    db.parent.mkdir()
    db.write_bytes(b"database-test")
    monkeypatch.setattr("src.backup_tools.DB_PATH", db)

    backup = crea_backup_database("prima_test")

    assert backup is not None
    assert Path(backup).exists()
    assert Path(backup).read_bytes() == b"database-test"
    assert Path(backup).parent == tmp_path / "backup"
    assert "prima_test" in Path(backup).name


def test_crea_backup_database_senza_db(tmp_path, monkeypatch):
    monkeypatch.setattr("src.backup_tools.DB_PATH", tmp_path / "data" / "missing.db")

    assert crea_backup_database("missing") is None
