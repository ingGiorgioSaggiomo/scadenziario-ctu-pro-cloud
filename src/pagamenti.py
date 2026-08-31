"""Calcoli riepilogativi per pagamenti e sospesi."""

from __future__ import annotations

from decimal import Decimal


TIPI_PAGAMENTO = ["acconto", "saldo", "altro"]
ALIQUOTA_CASSA_PREVIDENZIALE = Decimal("0.04")
MARCA_DA_BOLLO = Decimal("2.00")


def _money(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def calcola_cassa_previdenziale(imponibile) -> Decimal:
    """Calcola il contributo cassa 4% sull'imponibile."""
    return (_money(imponibile) * ALIQUOTA_CASSA_PREVIDENZIALE).quantize(Decimal("0.01"))


def calcola_totale_fattura(imponibile=0, spese=0, marca_bollo=True) -> dict[str, Decimal]:
    """Calcola totale dovuto in regime forfettario con cassa e bollo."""
    imponibile = _money(imponibile)
    spese = _money(spese)
    cassa = calcola_cassa_previdenziale(imponibile)
    bollo = MARCA_DA_BOLLO if marca_bollo and (imponibile + spese + cassa) > 0 else Decimal("0.00")
    totale = imponibile + spese + cassa + bollo
    return {
        "imponibile": imponibile,
        "spese": spese,
        "cassa": cassa,
        "bollo": bollo,
        "totale": totale,
    }


def importo_dovuto_pagamento(pagamento) -> Decimal:
    """Restituisce il dovuto calcolato o, per vecchi dati, quello salvato."""
    imponibile = _money(getattr(pagamento, "imponibile", 0))
    spese = _money(getattr(pagamento, "spese", 0))
    if imponibile or spese:
        return calcola_totale_fattura(imponibile, spese)["totale"]
    return _money(getattr(pagamento, "importo_dovuto", 0))


def riepilogo_pagamenti(pagamenti) -> dict[str, Decimal]:
    """Calcola liquidato, ricevuto e residuo.

    Ogni riga rappresenta un importo dovuto o ricevuto.
    Per il saldo finale va inserito l'importo ancora dovuto dopo avere detratto
    l'acconto gia' ricevuto. Il residuo e' quindi dato dalla somma degli importi
    dovuti meno la somma degli importi ricevuti.
    """
    righe = list(pagamenti or [])
    totale_ricevuto = sum((_money(getattr(p, "importo_ricevuto", 0)) for p in righe), Decimal("0.00"))
    acconti_ricevuti = sum(
        (
            _money(getattr(p, "importo_ricevuto", 0))
            for p in righe
            if getattr(p, "tipo", None) == "acconto"
        ),
        Decimal("0.00"),
    )
    totale_dovuto = sum((importo_dovuto_pagamento(p) for p in righe), Decimal("0.00"))
    residuo = totale_dovuto - totale_ricevuto
    if residuo < 0:
        residuo = Decimal("0.00")
    return {
        "totale_dovuto": totale_dovuto,
        "totale_ricevuto": totale_ricevuto,
        "acconti_ricevuti": acconti_ricevuti,
        "residuo": residuo,
    }


def fmt_euro(value) -> str:
    return f"{_money(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
