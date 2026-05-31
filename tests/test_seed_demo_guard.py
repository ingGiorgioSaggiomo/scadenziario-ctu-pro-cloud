"""Verifica che seed_demo non rigeneri dati se esistono incarichi reali."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import init_db, get_session
from src.models import Incarico


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    test_db = tmp_path / "seed.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db)
    new_engine = create_engine(f"sqlite:///{test_db}")
    monkeypatch.setattr("src.database.engine", new_engine)
    monkeypatch.setattr("src.database.SessionLocal", sessionmaker(bind=new_engine))
    init_db()
    yield


def test_seed_skippa_se_dati_reali_presenti(isolated_db, capsys):
    from src.seed_demo import seed
    s = get_session()
    s.add(Incarico(
        tipo="CTU", numero_rg="REAL/1", tribunale="T",
        data_conferimento=date.today(), origine_dato="manuale",
    ))
    s.commit()
    s.close()

    seed()
    captured = capsys.readouterr()
    assert "annullato" in captured.out.lower()

    s = get_session()
    incs = s.query(Incarico).all()
    # Solo l'incarico reale, nessun demo aggiunto
    assert len(incs) == 1
    assert incs[0].numero_rg == "REAL/1"
    s.close()


def test_seed_funziona_su_db_vuoto(isolated_db):
    from src.seed_demo import seed
    seed()
    s = get_session()
    incs = s.query(Incarico).all()
    assert len(incs) >= 3
    assert all(i.origine_dato == "demo" for i in incs)
    s.close()
