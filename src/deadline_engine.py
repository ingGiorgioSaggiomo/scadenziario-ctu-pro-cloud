"""Motore di calcolo scadenze per incarichi CTU/Procura/RESA."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class ScadenzaCalcolata:
    tipo_termine: str
    data_scadenza: date
    giorni_residui: int
    alert: str
    completato: bool
    termine_id: Optional[int] = None


def calcola_data_scadenza(base_date: date, giorni: int) -> date:
    """Restituisce base_date + giorni naturali."""
    return base_date + timedelta(days=giorni)


def applica_sospensioni(incarico, base_date: date, data_scadenza: date) -> date:
    """Sposta la scadenza per le sospensioni chiuse che incidono sul termine."""
    intervalli = []
    for sospensione in getattr(incarico, "sospensioni", []) or []:
        if not getattr(sospensione, "incide_su_scadenze", False):
            continue
        data_inizio = getattr(sospensione, "data_inizio", None)
        data_fine = getattr(sospensione, "data_fine", None)
        if data_inizio is None or data_fine is None or data_fine < base_date:
            continue
        intervalli.append((max(data_inizio, base_date), data_fine))

    if not intervalli:
        return data_scadenza

    intervalli.sort()
    uniti = []
    for data_inizio, data_fine in intervalli:
        if uniti and data_inizio <= uniti[-1][1] + timedelta(days=1):
            precedente_inizio, precedente_fine = uniti[-1]
            uniti[-1] = (precedente_inizio, max(precedente_fine, data_fine))
        else:
            uniti.append((data_inizio, data_fine))

    risultato = data_scadenza
    for data_inizio, data_fine in uniti:
        if data_inizio > risultato:
            break
        risultato += timedelta(days=(data_fine - data_inizio).days + 1)
    return risultato


def risolvi_data_decorrenza(incarico, termine) -> Optional[date]:
    """Determina la data base da cui decorre un termine, in base al campo decorrenza."""
    mapping = {
        "data_nomina": incarico.data_conferimento,
        "data_giuramento": incarico.data_giuramento,
        "data_inizio_operazioni": incarico.data_inizio_operazioni,
        "data_invio_bozza": incarico.data_invio_bozza,
        "data_ricezione_osservazioni": incarico.data_ricezione_osservazioni,
        "data_manual": termine.data_manual,
    }
    if termine.decorrenza == "data_scadenza_osservazioni":
        termine_oss = _trova_termine_osservazioni(incarico)
        if termine_oss and termine_oss.data_scadenza:
            return termine_oss.data_scadenza
        return None
    return mapping.get(termine.decorrenza)


def _trova_termine_osservazioni(incarico) -> Optional[object]:
    """Cerca il termine di tipo 'osservazioni' nell'incarico."""
    for t in incarico.termini:
        if t.tipo_termine == "osservazioni" and t.attivo:
            return t
    return None


def genera_eventi_standard(
    incarico,
    termini: list,
    data_oggi: Optional[date] = None,
) -> list[ScadenzaCalcolata]:
    """Genera eventi calcolati per ogni termine attivo e non completato."""
    oggi = data_oggi or date.today()
    risultati = []

    for termine in termini:
        if not termine.attivo:
            continue

        base = risolvi_data_decorrenza(incarico, termine)
        if base is None:
            continue

        if termine.decorrenza == "data_manual":
            data_scad = base
        else:
            data_scad = calcola_data_scadenza(base, termine.giorni)
            data_scad = applica_sospensioni(incarico, base, data_scad)
        giorni_res = calcola_giorni_residui(data_scad, oggi)
        alert = classifica_alert(giorni_res, incarico.stato)

        risultati.append(ScadenzaCalcolata(
            tipo_termine=termine.tipo_termine,
            data_scadenza=data_scad,
            giorni_residui=giorni_res,
            alert=alert,
            completato=termine.completato,
            termine_id=getattr(termine, "id", None),
        ))

    return risultati


def trova_prossima_scadenza(
    eventi: list[ScadenzaCalcolata],
    data_oggi: date,
) -> Optional[ScadenzaCalcolata]:
    """Trova la prossima scadenza non completata, ordinata per data crescente.

    Include eventi già scaduti (giorni_residui < 0).
    Esclude eventi completati.
    """
    attivi = [e for e in eventi if not e.completato]
    if not attivi:
        return None
    attivi.sort(key=lambda e: e.data_scadenza)
    return attivi[0]


def calcola_giorni_residui(data_scadenza: date, data_oggi: date) -> int:
    """Restituisce intero positivo, zero o negativo."""
    return (data_scadenza - data_oggi).days


def classifica_alert(giorni_residui: int, stato_incarico: str) -> str:
    """Classifica il livello di alert in base a giorni residui e stato."""
    if stato_incarico == "chiuso":
        return "chiuso"
    if stato_incarico == "sospeso":
        return "sospeso"
    if stato_incarico == "attesa osservazioni":
        return "attesa_osservazioni"
    if giorni_residui < 0:
        return "scaduto"
    if giorni_residui <= 3:
        return "critico"
    if giorni_residui <= 10:
        return "urgente"
    if giorni_residui <= 30:
        return "pianificare"
    return "regolare"
