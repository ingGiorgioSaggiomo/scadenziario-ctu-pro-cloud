"""Test per la logica di classificazione e gestione dati nella dashboard."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import elimina_dati_demo, elimina_incarico, init_db
from src.models import Incarico
from src.utils import (
    calcola_scadenza_termine,
    classifica_per_dashboard,
    is_numero_da_correggere,
    stato_evento,
    applica_stato_evento,
    trova_prossima_attivita_dashboard,
)


@dataclass
class FakeProssima:
    giorni_residui: int


# ----- classifica_per_dashboard -----

def test_dashboard_attivo_senza_scadenze_e_dati_mancanti():
    assert classifica_per_dashboard("attivo", None) == "dati_mancanti"


def test_dashboard_attivo_con_scadenza_usa_motore():
    assert classifica_per_dashboard("attivo", FakeProssima(giorni_residui=20)) == "pianificare"
    assert classifica_per_dashboard("attivo", FakeProssima(giorni_residui=2)) == "critico"
    assert classifica_per_dashboard("attivo", FakeProssima(giorni_residui=-1)) == "scaduto"


def test_dashboard_chiuso_e_sospeso_prevalgono():
    assert classifica_per_dashboard("chiuso", FakeProssima(giorni_residui=5)) == "chiuso"
    assert classifica_per_dashboard("sospeso", FakeProssima(giorni_residui=5)) == "sospeso"
    assert classifica_per_dashboard("chiuso", None) == "chiuso"
    assert classifica_per_dashboard("sospeso", None) == "sospeso"


def test_dashboard_attesa_osservazioni_prevale():
    assert classifica_per_dashboard("attesa osservazioni", FakeProssima(giorni_residui=-5)) == "attesa_osservazioni"
    assert classifica_per_dashboard("attesa osservazioni", None) == "attesa_osservazioni"


@dataclass
class FakeEvento:
    tipo: str
    data: Optional[date]
    completato: bool = False
    annullato: bool = False


@dataclass
class FakeTermine:
    tipo_termine: str = "bozza"
    giorni: int = 10
    decorrenza: str = "data_inizio_operazioni"
    data_manual: Optional[date] = None
    attivo: bool = True
    completato: bool = False


@dataclass
class FakeIncaricoDashboard:
    stato: str = "attivo"
    termini: list = None
    eventi: list = None
    data_conferimento: Optional[date] = None
    data_giuramento: Optional[date] = None
    data_inizio_operazioni: Optional[date] = None
    data_invio_bozza: Optional[date] = None
    data_ricezione_osservazioni: Optional[date] = None

    def __post_init__(self):
        if self.termini is None:
            self.termini = []
        if self.eventi is None:
            self.eventi = []


def test_dashboard_evento_futuro_senza_termini():
    oggi = date(2026, 5, 2)
    inc = FakeIncaricoDashboard(
        eventi=[FakeEvento(tipo="udienza", data=oggi + timedelta(days=7))]
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is not None
    assert prossima.tipo_termine == "udienza"
    assert prossima.data_scadenza == oggi + timedelta(days=7)
    assert prossima.giorni_residui == 7
    assert classifica_per_dashboard(inc.stato, prossima) == "urgente"


def test_dashboard_evento_scaduto_senza_termini():
    oggi = date(2026, 5, 2)
    inc = FakeIncaricoDashboard(
        eventi=[FakeEvento(tipo="deposito", data=oggi - timedelta(days=2))]
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is not None
    assert prossima.tipo_termine == "deposito"
    assert prossima.giorni_residui == -2
    assert classifica_per_dashboard(inc.stato, prossima) == "scaduto"


def test_dashboard_evento_completato_ignorato():
    oggi = date(2026, 5, 2)
    inc = FakeIncaricoDashboard(
        eventi=[FakeEvento(tipo="bozza", data=oggi + timedelta(days=5), completato=True)]
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is None
    assert classifica_per_dashboard(inc.stato, prossima) == "dati_mancanti"


def test_dashboard_evento_annullato_ignorato():
    oggi = date(2026, 5, 2)
    inc = FakeIncaricoDashboard(
        eventi=[FakeEvento(tipo="udienza", data=oggi + timedelta(days=5), annullato=True)]
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is None
    assert classifica_per_dashboard(inc.stato, prossima) == "dati_mancanti"


def test_dashboard_evento_nota_non_supera_termine_operativo():
    oggi = date(2026, 6, 24)
    inc = FakeIncaricoDashboard(
        termini=[
            FakeTermine(
                tipo_termine="bozza",
                giorni=0,
                decorrenza="data_manual",
                data_manual=date(2026, 7, 31),
            )
        ],
        eventi=[FakeEvento(tipo="nota", data=date(2026, 6, 12))],
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is not None
    assert prossima.tipo_termine == "bozza"
    assert prossima.data_scadenza == date(2026, 7, 31)


def test_dashboard_termine_nota_non_supera_termine_operativo():
    oggi = date(2026, 6, 24)
    inc = FakeIncaricoDashboard(
        termini=[
            FakeTermine(
                tipo_termine="nota",
                giorni=0,
                decorrenza="data_manual",
                data_manual=date(2026, 6, 12),
            ),
            FakeTermine(
                tipo_termine="bozza",
                giorni=0,
                decorrenza="data_manual",
                data_manual=date(2026, 7, 31),
            ),
        ],
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is not None
    assert prossima.tipo_termine == "bozza"
    assert prossima.data_scadenza == date(2026, 7, 31)


def test_dashboard_senza_termini_e_senza_eventi_validi():
    oggi = date(2026, 5, 2)
    inc = FakeIncaricoDashboard()
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is None
    assert classifica_per_dashboard(inc.stato, prossima) == "dati_mancanti"


def test_dashboard_attesa_osservazioni_slitta_a_deposito_evento():
    oggi = date(2026, 5, 2)
    inc = FakeIncaricoDashboard(
        stato="attesa osservazioni",
        eventi=[
            FakeEvento(tipo="osservazioni", data=oggi + timedelta(days=3)),
            FakeEvento(tipo="deposito", data=oggi + timedelta(days=30)),
        ],
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is not None
    assert prossima.tipo_termine == "deposito"
    assert prossima.data_scadenza == oggi + timedelta(days=30)
    assert classifica_per_dashboard(inc.stato, prossima) == "pianificare"


def test_dashboard_attesa_osservazioni_slitta_a_deposito_termine():
    oggi = date.today()
    inc = FakeIncaricoDashboard(
        stato="attesa osservazioni",
        termini=[
            FakeTermine(tipo_termine="osservazioni", giorni=0, decorrenza="data_manual", data_manual=oggi + timedelta(days=3)),
            FakeTermine(tipo_termine="deposito", giorni=0, decorrenza="data_manual", data_manual=oggi + timedelta(days=9)),
        ],
    )
    prossima = trova_prossima_attivita_dashboard(inc, oggi)
    assert prossima is not None
    assert prossima.tipo_termine == "deposito"
    assert prossima.data_scadenza == oggi + timedelta(days=9)
    assert classifica_per_dashboard(inc.stato, prossima) == "urgente"


def test_calcola_scadenza_termine_con_date_python():
    inc = FakeIncaricoDashboard(data_inizio_operazioni=date(2026, 5, 1))
    term = FakeTermine(giorni=5, decorrenza="data_inizio_operazioni")
    assert calcola_scadenza_termine(inc, term) == date(2026, 5, 6)


# ----- is_numero_da_correggere -----

def test_numero_import_da_correggere():
    assert is_numero_da_correggere("IMPORT-2") is True
    assert is_numero_da_correggere("IMPORT-99") is True
    assert is_numero_da_correggere("1234/2025") is False
    assert is_numero_da_correggere("") is True
    assert is_numero_da_correggere(None) is True


# ----- stato evento -----

def test_stato_evento_e_applicazione():
    @dataclass
    class FakeEv:
        completato: bool = False
        annullato: bool = False

    e = FakeEv()
    assert stato_evento(e) == "previsto"
    applica_stato_evento(e, "completato")
    assert e.completato and not e.annullato
    assert stato_evento(e) == "completato"
    applica_stato_evento(e, "annullato")
    assert e.annullato and not e.completato
    assert stato_evento(e) == "annullato"
    applica_stato_evento(e, "previsto")
    assert not e.completato and not e.annullato


# ----- elimina_dati_demo -----

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    test_db = tmp_path / "dash.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db)
    new_engine = create_engine(f"sqlite:///{test_db}")
    monkeypatch.setattr("src.database.engine", new_engine)
    monkeypatch.setattr("src.database.SessionLocal", sessionmaker(bind=new_engine))
    init_db()
    yield


def test_elimina_dati_demo(isolated_db):
    from src.database import get_session
    s = get_session()
    s.add(Incarico(
        tipo="CTU", numero_rg="DEMO/1", tribunale="T",
        data_conferimento=date.today(), origine_dato="demo",
    ))
    s.add(Incarico(
        tipo="CTU", numero_rg="REAL/1", tribunale="T",
        data_conferimento=date.today(), origine_dato="manuale",
    ))
    s.commit()
    s.close()

    s = get_session()
    eliminati = elimina_dati_demo(s)
    assert eliminati == 1
    rimasti = s.query(Incarico).all()
    assert len(rimasti) == 1
    assert rimasti[0].numero_rg == "REAL/1"
    s.close()


def test_elimina_dati_demo_nessuno(isolated_db):
    from src.database import get_session
    s = get_session()
    s.add(Incarico(
        tipo="CTU", numero_rg="REAL/1", tribunale="T",
        data_conferimento=date.today(), origine_dato="manuale",
    ))
    s.commit()
    eliminati = elimina_dati_demo(s)
    assert eliminati == 0
    s.close()


def test_elimina_dati_demo_cascade_su_figli(isolated_db):
    """L'eliminazione di un incarico demo deve rimuovere anche termini, eventi,
    sospensioni e documenti collegati."""
    from src.database import get_session
    from src.models import Documento, Evento, Sospensione, Termine

    s = get_session()
    demo = Incarico(
        tipo="CTU", numero_rg="DEMO/CASCADE", tribunale="T",
        data_conferimento=date.today(), origine_dato="demo",
    )
    demo.termini = [Termine(
        tipo_termine="bozza", giorni=60, decorrenza="data_nomina",
        tipo_computo="naturali",
    )]
    demo.eventi = [Evento(tipo="udienza", data=date.today() + timedelta(days=10))]
    demo.sospensioni = [Sospensione(data_inizio=date.today())]
    demo.documenti = [Documento(nome="all1.pdf", tipo="allegato")]

    real = Incarico(
        tipo="CTU", numero_rg="REAL/KEEP", tribunale="T",
        data_conferimento=date.today(), origine_dato="manuale",
    )
    real.termini = [Termine(
        tipo_termine="deposito", giorni=30, decorrenza="data_nomina",
        tipo_computo="naturali",
    )]
    real.eventi = [Evento(tipo="udienza", data=date.today() + timedelta(days=20))]

    s.add_all([demo, real])
    s.commit()
    s.close()

    s = get_session()
    eliminati = elimina_dati_demo(s)
    assert eliminati == 1
    # Figli del demo eliminati, figli del reale preservati
    assert s.query(Incarico).count() == 1
    assert s.query(Termine).count() == 1
    assert s.query(Evento).count() == 1
    assert s.query(Sospensione).count() == 0
    assert s.query(Documento).count() == 0
    rimasto = s.query(Incarico).one()
    assert rimasto.numero_rg == "REAL/KEEP"
    s.close()


def test_elimina_dati_demo_committa(isolated_db):
    """Dopo elimina_dati_demo i dati devono essere persistiti (commit)."""
    from src.database import get_session
    s = get_session()
    s.add(Incarico(
        tipo="CTU", numero_rg="DEMO/X", tribunale="T",
        data_conferimento=date.today(), origine_dato="demo",
    ))
    s.commit()
    elimina_dati_demo(s)
    s.close()
    # Sessione nuova: la cancellazione deve essere persistente
    s2 = get_session()
    assert s2.query(Incarico).count() == 0
    s2.close()


def test_elimina_incarico_cascade_su_figli(isolated_db):
    from src.database import get_session
    from src.models import Documento, Evento, Sospensione, Termine

    s = get_session()
    inc = Incarico(
        tipo="CTU", numero_rg="DEL/1", tribunale="T",
        data_conferimento=date.today(), origine_dato="manuale",
    )
    inc.termini = [Termine(
        tipo_termine="bozza", giorni=10, decorrenza="data_nomina",
        tipo_computo="naturali",
    )]
    inc.eventi = [Evento(tipo="udienza", data=date.today() + timedelta(days=3))]
    inc.sospensioni = [Sospensione(data_inizio=date.today())]
    inc.documenti = [Documento(nome="doc.pdf", tipo="allegato")]
    s.add(inc)
    s.commit()
    inc_id = inc.id
    s.close()

    s = get_session()
    assert elimina_incarico(s, inc_id) is True
    assert s.query(Incarico).count() == 0
    assert s.query(Termine).count() == 0
    assert s.query(Evento).count() == 0
    assert s.query(Sospensione).count() == 0
    assert s.query(Documento).count() == 0
    s.close()


def test_elimina_incarico_non_trovato(isolated_db):
    from src.database import get_session

    s = get_session()
    assert elimina_incarico(s, 999999) is False
    s.close()
