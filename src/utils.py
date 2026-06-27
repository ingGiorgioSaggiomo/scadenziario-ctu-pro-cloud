"""Utility comuni: colori alert, ordinamento, helper UI."""

from datetime import date
from typing import Optional

ALERT_COLORS = {
    "scaduto": "#c62828",
    "critico": "#ef6c00",
    "urgente": "#f9a825",
    "pianificare": "#1565c0",
    "regolare": "#2e7d32",
    "attesa_osservazioni": "#607d8b",
    "sospeso": "#6a1b9a",
    "chiuso": "#546e7a",
    "dati_mancanti": "#90a4ae",
}

ALERT_PRIORITY = {
    "scaduto": 0,
    "critico": 1,
    "urgente": 2,
    "pianificare": 3,
    "dati_mancanti": 4,
    "regolare": 5,
    "attesa_osservazioni": 6,
    "sospeso": 7,
    "chiuso": 8,
}

ALERT_LABEL = {
    "scaduto": "scaduto",
    "critico": "critico",
    "urgente": "urgente",
    "pianificare": "pianificare",
    "regolare": "regolare",
    "attesa_osservazioni": "attesa osservazioni",
    "sospeso": "sospeso",
    "chiuso": "chiuso",
    "dati_mancanti": "dati mancanti",
}

TIPI_INCARICO = ["CTU", "Procura", "RESA", "Ordine a fare", "Incarico tecnico"]
STATI_INCARICO = ["attivo", "attesa osservazioni", "sospeso", "chiuso"]
PRIORITA = ["alta", "media", "bassa"]
ORIGINI_DATO = ["manuale", "import_excel", "demo"]
TIPI_TERMINE = ["bozza", "osservazioni", "deposito", "udienza", "personalizzato"]
DECORRENZE = [
    "data_nomina",
    "data_giuramento",
    "data_inizio_operazioni",
    "data_invio_bozza",
    "data_scadenza_osservazioni",
    "data_ricezione_osservazioni",
    "data_manual",
]
TIPI_EVENTO = ["udienza", "sopralluogo", "riunione", "deposito", "bozza", "osservazioni", "nota", "altro"]
STATI_EVENTO = ["previsto", "completato", "annullato"]
TIPI_EVENTO_NON_OPERATIVI_DASHBOARD = {"nota"}


def alert_badge_html(alert: str) -> str:
    color = ALERT_COLORS.get(alert, "#9e9e9e")
    label = ALERT_LABEL.get(alert, alert)
    return (
        f'<span style="background-color:{color};color:white;'
        f'padding:2px 10px;border-radius:10px;font-size:0.85em;'
        f'font-weight:600;text-transform:uppercase">{label}</span>'
    )


def fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def calcola_scadenza_termine(incarico, termine) -> Optional[date]:
    """Calcola la scadenza di un termine usando la logica esistente."""
    from src.deadline_engine import calcola_data_scadenza, risolvi_data_decorrenza

    base = risolvi_data_decorrenza(incarico, termine)
    if base is None:
        return None
    return calcola_data_scadenza(base, int(termine.giorni or 0))


def classifica_per_dashboard(stato_incarico: str, prossima_scadenza) -> str:
    """Determina l'alert per la riga di dashboard di un incarico.

    A differenza di deadline_engine.classifica_alert (che opera su una
    scadenza concreta), questa funzione gestisce anche il caso in cui
    l'incarico attivo non abbia alcuna scadenza valida: in quel caso
    restituisce 'dati_mancanti'.
    """
    if stato_incarico == "chiuso":
        return "chiuso"
    if stato_incarico == "sospeso":
        return "sospeso"
    if stato_incarico == "attesa osservazioni":
        if prossima_scadenza is not None and getattr(prossima_scadenza, "tipo_termine", None) == "deposito":
            from src.deadline_engine import classifica_alert
            return classifica_alert(prossima_scadenza.giorni_residui, "attivo")
        return "attesa_osservazioni"
    if prossima_scadenza is None:
        return "dati_mancanti"
    from src.deadline_engine import classifica_alert
    return classifica_alert(prossima_scadenza.giorni_residui, stato_incarico)


def _usa_deposito_in_attesa_osservazioni(incarico, eventi):
    if getattr(incarico, "stato", None) != "attesa osservazioni":
        return eventi

    depositi = [e for e in eventi if e.tipo_termine == "deposito"]
    if depositi:
        return depositi
    return [e for e in eventi if e.tipo_termine not in {"bozza", "osservazioni"}]


def trova_prossima_attivita_dashboard(incarico, data_oggi: Optional[date] = None):
    """Combina scadenze calcolate e eventi DB per la dashboard."""
    from src.deadline_engine import (
        ScadenzaCalcolata,
        calcola_giorni_residui,
        classifica_alert,
        genera_eventi_standard,
        trova_prossima_scadenza,
    )

    if data_oggi is None:
        data_oggi = date.today()

    eventi = [
        evento
        for evento in genera_eventi_standard(incarico, incarico.termini)
        if getattr(evento, "tipo_termine", None) not in TIPI_EVENTO_NON_OPERATIVI_DASHBOARD
    ]
    for evento in incarico.eventi:
        if getattr(evento, "tipo", None) in TIPI_EVENTO_NON_OPERATIVI_DASHBOARD:
            continue
        if evento.data is None:
            continue
        if getattr(evento, "completato", False):
            continue
        if getattr(evento, "annullato", False):
            continue
        giorni_residui = calcola_giorni_residui(evento.data, data_oggi)
        eventi.append(ScadenzaCalcolata(
            tipo_termine=evento.tipo,
            data_scadenza=evento.data,
            giorni_residui=giorni_residui,
            alert=classifica_alert(giorni_residui, incarico.stato),
            completato=False,
        ))

    eventi = _usa_deposito_in_attesa_osservazioni(incarico, eventi)
    return trova_prossima_scadenza(eventi, data_oggi)


def is_numero_da_correggere(numero_rg: Optional[str]) -> bool:
    """True se il numero procedura è un placeholder dell'import Excel."""
    if not numero_rg:
        return True
    return numero_rg.startswith("IMPORT-")


def stato_evento(evento) -> str:
    """Restituisce 'previsto', 'completato' o 'annullato' per un Evento."""
    if getattr(evento, "annullato", False):
        return "annullato"
    if getattr(evento, "completato", False):
        return "completato"
    return "previsto"


def applica_stato_evento(evento, nuovo_stato: str) -> None:
    """Aggiorna i flag completato/annullato in base al nuovo stato."""
    evento.completato = nuovo_stato == "completato"
    evento.annullato = nuovo_stato == "annullato"
