"""Test per riepilogo pagamenti e sospesi."""

from decimal import Decimal
from types import SimpleNamespace

from src.pagamenti import calcola_totale_fattura, fmt_euro, riepilogo_pagamenti


def test_calcola_totale_fattura_forfettario_con_cassa_e_bollo():
    calcolo = calcola_totale_fattura(Decimal("1000"), Decimal("150"))

    assert calcolo["imponibile"] == Decimal("1000.00")
    assert calcolo["spese"] == Decimal("150.00")
    assert calcolo["cassa"] == Decimal("40.00")
    assert calcolo["bollo"] == Decimal("2.00")
    assert calcolo["totale"] == Decimal("1192.00")


def test_riepilogo_senza_saldo_somma_righe():
    pagamenti = [
        SimpleNamespace(tipo="acconto", importo_dovuto=Decimal("1000"), importo_ricevuto=Decimal("600")),
        SimpleNamespace(tipo="altro", importo_dovuto=Decimal("200"), importo_ricevuto=Decimal("0")),
    ]

    riepilogo = riepilogo_pagamenti(pagamenti)

    assert riepilogo["totale_dovuto"] == Decimal("1200.00")
    assert riepilogo["totale_ricevuto"] == Decimal("600.00")
    assert riepilogo["acconti_ricevuti"] == Decimal("600.00")
    assert riepilogo["residuo"] == Decimal("600.00")


def test_riepilogo_con_saldo_netto_non_pagato():
    pagamenti = [
        SimpleNamespace(tipo="acconto", importo_dovuto=Decimal("1000"), importo_ricevuto=Decimal("1000")),
        SimpleNamespace(
            tipo="saldo",
            imponibile=Decimal("2000"),
            spese=Decimal("418"),
            importo_dovuto=Decimal("0"),
            importo_ricevuto=Decimal("0"),
        ),
    ]

    riepilogo = riepilogo_pagamenti(pagamenti)

    assert riepilogo["totale_dovuto"] == Decimal("3500.00")
    assert riepilogo["totale_ricevuto"] == Decimal("1000.00")
    assert riepilogo["residuo"] == Decimal("2500.00")


def test_riepilogo_con_saldo_netto_pagato_chiude_residuo():
    pagamenti = [
        SimpleNamespace(tipo="acconto", importo_dovuto=Decimal("1000"), importo_ricevuto=Decimal("1000")),
        SimpleNamespace(tipo="saldo", importo_dovuto=Decimal("2500"), importo_ricevuto=Decimal("2500")),
    ]

    riepilogo = riepilogo_pagamenti(pagamenti)

    assert riepilogo["totale_dovuto"] == Decimal("3500.00")
    assert riepilogo["totale_ricevuto"] == Decimal("3500.00")
    assert riepilogo["residuo"] == Decimal("0.00")


def test_fmt_euro_italiano():
    assert fmt_euro(Decimal("1234.5")) == "1.234,50"
