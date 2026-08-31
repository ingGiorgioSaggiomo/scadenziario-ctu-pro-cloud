"""Test ordinamento cronologico termini in app."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app import PAGES, _termini_in_ordine_cronologico


@dataclass
class FakeTermine:
    id: int
    tipo_termine: str
    giorni: int
    decorrenza: str
    data_manual: Optional[date] = None


@dataclass
class FakeIncarico:
    data_conferimento: date
    termini: list
    data_giuramento: Optional[date] = None
    data_inizio_operazioni: Optional[date] = None
    data_invio_bozza: Optional[date] = None
    data_ricezione_osservazioni: Optional[date] = None


def test_termini_in_ordine_cronologico():
    inc = FakeIncarico(
        data_conferimento=date(2026, 1, 1),
        termini=[
            FakeTermine(16, "deposito", 0, "data_manual", date(2026, 9, 14)),
            FakeTermine(18, "personalizzato", 0, "data_inizio_operazioni"),
            FakeTermine(20, "osservazioni", 0, "data_manual", date(2026, 7, 25)),
            FakeTermine(22, "bozza", 0, "data_manual", date(2026, 7, 5)),
        ],
    )

    ordinati = _termini_in_ordine_cronologico(inc)

    assert [t.id for t in ordinati] == [22, 20, 16, 18]


def test_import_excel_raccolto_in_amministrazione_dati():
    assert "Amministrazione dati" in PAGES
    assert "Import Excel" not in PAGES
    assert "Verifica import" not in PAGES
