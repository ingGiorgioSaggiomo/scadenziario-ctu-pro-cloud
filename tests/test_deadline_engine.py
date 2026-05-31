"""Test unitari per il motore di calcolo scadenze."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from src.deadline_engine import (
    calcola_data_scadenza,
    calcola_giorni_residui,
    classifica_alert,
    genera_eventi_standard,
    trova_prossima_scadenza,
    ScadenzaCalcolata,
)


@dataclass
class FakeTermine:
    tipo_termine: str
    giorni: int
    decorrenza: str
    data_manual: Optional[date] = None
    attivo: bool = True
    completato: bool = False
    data_scadenza: Optional[date] = None


@dataclass
class FakeIncarico:
    data_conferimento: date
    data_giuramento: Optional[date] = None
    data_inizio_operazioni: Optional[date] = None
    data_invio_bozza: Optional[date] = None
    data_ricezione_osservazioni: Optional[date] = None
    stato: str = "attivo"
    termini: list = None

    def __post_init__(self):
        if self.termini is None:
            self.termini = []


# --- calcola_data_scadenza ---

def test_calcola_data_scadenza_base():
    base = date(2025, 3, 10)
    assert calcola_data_scadenza(base, 60) == date(2025, 5, 9)


def test_calcola_data_scadenza_zero_giorni():
    base = date(2025, 1, 1)
    assert calcola_data_scadenza(base, 0) == base


# --- calcolo bozza da inizio operazioni ---

def test_calcolo_bozza_da_inizio_operazioni():
    termine_bozza = FakeTermine(
        tipo_termine="bozza",
        giorni=90,
        decorrenza="data_inizio_operazioni",
    )
    incarico = FakeIncarico(
        data_conferimento=date(2025, 3, 1),
        data_inizio_operazioni=date(2025, 3, 20),
        termini=[termine_bozza],
    )

    eventi = genera_eventi_standard(incarico, [termine_bozza])
    assert len(eventi) == 1
    assert eventi[0].tipo_termine == "bozza"
    assert eventi[0].data_scadenza == date(2025, 3, 20) + timedelta(days=90)


# --- calcolo osservazioni da invio bozza ---

def test_calcolo_osservazioni_da_invio_bozza():
    termine_oss = FakeTermine(
        tipo_termine="osservazioni",
        giorni=30,
        decorrenza="data_invio_bozza",
    )
    incarico = FakeIncarico(
        data_conferimento=date(2025, 3, 1),
        data_invio_bozza=date(2025, 6, 18),
        termini=[termine_oss],
    )

    eventi = genera_eventi_standard(incarico, [termine_oss])
    assert len(eventi) == 1
    assert eventi[0].tipo_termine == "osservazioni"
    assert eventi[0].data_scadenza == date(2025, 7, 18)


# --- calcolo deposito da scadenza osservazioni ---

def test_calcolo_deposito_da_scadenza_osservazioni():
    termine_oss = FakeTermine(
        tipo_termine="osservazioni",
        giorni=30,
        decorrenza="data_invio_bozza",
        data_scadenza=date(2025, 7, 18),
    )
    termine_deposito = FakeTermine(
        tipo_termine="deposito",
        giorni=30,
        decorrenza="data_scadenza_osservazioni",
    )
    incarico = FakeIncarico(
        data_conferimento=date(2025, 3, 1),
        data_invio_bozza=date(2025, 6, 18),
        termini=[termine_oss, termine_deposito],
    )

    eventi = genera_eventi_standard(incarico, [termine_deposito])
    assert len(eventi) == 1
    assert eventi[0].tipo_termine == "deposito"
    assert eventi[0].data_scadenza == date(2025, 8, 17)


# --- riconoscimento scadenza già superata ---

def test_scadenza_gia_superata():
    ieri = date.today() - timedelta(days=5)
    termine = FakeTermine(
        tipo_termine="bozza",
        giorni=0,
        decorrenza="data_inizio_operazioni",
    )
    incarico = FakeIncarico(
        data_conferimento=date(2025, 1, 1),
        data_inizio_operazioni=ieri,
        termini=[termine],
    )

    eventi = genera_eventi_standard(incarico, [termine])
    assert len(eventi) == 1
    assert eventi[0].giorni_residui < 0
    assert eventi[0].alert == "scaduto"


# --- esclusione eventi completati da trova_prossima_scadenza ---

def test_esclusione_eventi_completati():
    oggi = date.today()
    eventi = [
        ScadenzaCalcolata("bozza", oggi + timedelta(days=5), 5, "critico", completato=True),
        ScadenzaCalcolata("deposito", oggi + timedelta(days=20), 20, "pianificare", completato=False),
        ScadenzaCalcolata("osservazioni", oggi + timedelta(days=10), 10, "urgente", completato=False),
    ]

    prossima = trova_prossima_scadenza(eventi, oggi)
    assert prossima is not None
    assert prossima.tipo_termine == "osservazioni"


def test_tutti_completati_restituisce_none():
    oggi = date.today()
    eventi = [
        ScadenzaCalcolata("bozza", oggi + timedelta(days=5), 5, "critico", completato=True),
        ScadenzaCalcolata("deposito", oggi + timedelta(days=20), 20, "pianificare", completato=True),
    ]

    assert trova_prossima_scadenza(eventi, oggi) is None


# --- trova_prossima_scadenza include scaduti ---

def test_trova_prossima_include_scaduti():
    oggi = date.today()
    eventi = [
        ScadenzaCalcolata("bozza", oggi - timedelta(days=3), -3, "scaduto", completato=False),
        ScadenzaCalcolata("deposito", oggi + timedelta(days=20), 20, "pianificare", completato=False),
    ]

    prossima = trova_prossima_scadenza(eventi, oggi)
    assert prossima.tipo_termine == "bozza"
    assert prossima.giorni_residui == -3


# --- calcola_giorni_residui ---

def test_giorni_residui_positivi():
    assert calcola_giorni_residui(date(2025, 6, 10), date(2025, 6, 1)) == 9


def test_giorni_residui_zero():
    oggi = date.today()
    assert calcola_giorni_residui(oggi, oggi) == 0


def test_giorni_residui_negativi():
    assert calcola_giorni_residui(date(2025, 5, 1), date(2025, 5, 10)) == -9


# --- classifica_alert ---

def test_alert_chiuso():
    assert classifica_alert(15, "chiuso") == "chiuso"


def test_alert_sospeso():
    assert classifica_alert(15, "sospeso") == "sospeso"


def test_alert_attesa_osservazioni():
    assert classifica_alert(-10, "attesa osservazioni") == "attesa_osservazioni"


def test_alert_scaduto():
    assert classifica_alert(-1, "attivo") == "scaduto"


def test_alert_critico():
    assert classifica_alert(0, "attivo") == "critico"
    assert classifica_alert(3, "attivo") == "critico"


def test_alert_urgente():
    assert classifica_alert(4, "attivo") == "urgente"
    assert classifica_alert(10, "attivo") == "urgente"


def test_alert_pianificare():
    assert classifica_alert(11, "attivo") == "pianificare"
    assert classifica_alert(30, "attivo") == "pianificare"


def test_alert_regolare():
    assert classifica_alert(31, "attivo") == "regolare"
    assert classifica_alert(100, "attivo") == "regolare"


# --- termine non attivo viene escluso ---

def test_termine_non_attivo_escluso():
    termine = FakeTermine(
        tipo_termine="bozza",
        giorni=60,
        decorrenza="data_inizio_operazioni",
        attivo=False,
    )
    incarico = FakeIncarico(
        data_conferimento=date(2025, 3, 1),
        data_inizio_operazioni=date(2025, 3, 20),
        termini=[termine],
    )

    eventi = genera_eventi_standard(incarico, [termine])
    assert len(eventi) == 0


# --- decorrenza data_manual ---

def test_decorrenza_data_manual():
    termine = FakeTermine(
        tipo_termine="personalizzato",
        giorni=15,
        decorrenza="data_manual",
        data_manual=date(2025, 4, 1),
    )
    incarico = FakeIncarico(
        data_conferimento=date(2025, 3, 1),
        termini=[termine],
    )

    eventi = genera_eventi_standard(incarico, [termine])
    assert len(eventi) == 1
    assert eventi[0].data_scadenza == date(2025, 4, 16)
