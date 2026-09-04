"""Coordinamento tra termini, eventi, workflow CTU e relativo storico."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.models import Evento, StoricoTermine, Termine
from src.utils import calcola_scadenza_termine


TIPI_SCADENZA_SINCRONIZZABILI = {"bozza", "osservazioni", "deposito", "udienza"}


@dataclass(frozen=True)
class Incongruenza:
    livello: str
    codice: str
    descrizione: str
    termine_id: Optional[int] = None
    evento_id: Optional[int] = None


def _tipo_normalizzato(valore) -> str:
    return str(valore or "").strip().lower()


def normalizza_impostazione_scadenza(
    decorrenza: str,
    giorni: int,
    data_manual: Optional[date],
) -> tuple[str, int, Optional[date]]:
    """Una data esatta inserita dall'utente prevale sul calcolo automatico."""
    if data_manual is not None:
        return "data_manual", 0, data_manual
    if decorrenza == "data_manual":
        raise ValueError("Inserisci la data di scadenza esatta.")
    return decorrenza, int(giorni or 0), None


def registra_storico_termine(session, termine: Termine, azione: str, motivo: Optional[str] = None):
    """Salva una fotografia del termine prima o dopo una variazione."""
    storico = StoricoTermine(
        incarico_id=termine.incarico_id,
        termine_id=termine.id,
        azione=azione,
        motivo=motivo or None,
        tipo_termine=termine.tipo_termine,
        giorni=int(termine.giorni or 0),
        decorrenza=termine.decorrenza,
        data_manual=termine.data_manual,
        data_scadenza=termine.data_scadenza,
        attivo=bool(termine.attivo),
        completato=bool(termine.completato),
        prorogato=bool(termine.prorogato),
        note=termine.note,
    )
    session.add(storico)
    return storico


def sincronizza_evento_da_termine(session, incarico, termine: Termine) -> Optional[Evento]:
    """Crea o aggiorna l'unico Evento esplicitamente collegato al Termine."""
    tipo = _tipo_normalizzato(termine.tipo_termine)
    if tipo not in TIPI_SCADENZA_SINCRONIZZABILI:
        return None

    if termine.id is None:
        session.flush()

    evento = session.query(Evento).filter(Evento.termine_id == termine.id).one_or_none()
    if evento is None:
        evento = Evento(
            incarico_id=incarico.id,
            termine_id=termine.id,
            tipo=termine.tipo_termine,
            descrizione="Sincronizzato automaticamente dal termine",
        )
        session.add(evento)

    evento.incarico_id = incarico.id
    evento.tipo = termine.tipo_termine
    evento.data = calcola_scadenza_termine(incarico, termine)
    evento.completato = bool(termine.completato)
    evento.annullato = not bool(termine.attivo)
    return evento


def scollega_evento_prima_eliminazione(session, termine: Termine) -> None:
    evento = session.query(Evento).filter(Evento.termine_id == termine.id).one_or_none()
    if evento is not None:
        evento.termine_id = None
        evento.annullato = True
        if not evento.descrizione:
            evento.descrizione = "Evento annullato per eliminazione del termine collegato"


def aggiorna_termine(
    session,
    incarico,
    termine: Termine,
    *,
    tipo_termine: str,
    giorni: int,
    decorrenza: str,
    data_manual: Optional[date],
    attivo: bool,
    completato: bool,
    prorogato: bool,
    note: Optional[str],
    motivo: Optional[str] = None,
) -> Termine:
    decorrenza, giorni, data_manual = normalizza_impostazione_scadenza(
        decorrenza,
        giorni,
        data_manual,
    )
    registra_storico_termine(session, termine, "prima_modifica", motivo)
    termine.tipo_termine = tipo_termine
    termine.decorrenza = decorrenza
    termine.giorni = giorni
    termine.data_manual = data_manual
    termine.attivo = bool(attivo)
    termine.completato = bool(completato)
    termine.prorogato = bool(prorogato)
    termine.note = note or None
    termine.data_scadenza = calcola_scadenza_termine(incarico, termine)
    sincronizza_evento_da_termine(session, incarico, termine)
    registra_storico_termine(session, termine, "dopo_modifica", motivo)
    return termine


def ricalcola_termini_incarico(session, incarico, motivo: str) -> int:
    """Ricalcola e sincronizza i termini cambiati dopo una nuova data di riferimento."""
    aggiornati = 0
    for termine in getattr(incarico, "termini", []):
        nuova_scadenza = calcola_scadenza_termine(incarico, termine)
        if nuova_scadenza == termine.data_scadenza:
            continue
        registra_storico_termine(session, termine, "prima_ricalcolo", motivo)
        termine.data_scadenza = nuova_scadenza
        sincronizza_evento_da_termine(session, incarico, termine)
        registra_storico_termine(session, termine, "dopo_ricalcolo", motivo)
        aggiornati += 1
    return aggiornati


def completa_bozza(session, incarico, termine: Termine, data_invio: date) -> None:
    registra_storico_termine(session, termine, "prima_completamento", "Invio bozza confermato")
    termine.completato = True
    incarico.data_invio_bozza = data_invio
    incarico.stato = "attesa osservazioni"
    sincronizza_evento_da_termine(session, incarico, termine)
    registra_storico_termine(session, termine, "completato", "Invio bozza confermato")
    ricalcola_termini_incarico(session, incarico, "Invio bozza confermato")


def completa_osservazioni(session, incarico, termine: Termine, data_fine_attesa: date) -> None:
    registra_storico_termine(session, termine, "prima_completamento", "Fine attesa osservazioni confermata")
    termine.completato = True
    incarico.data_ricezione_osservazioni = data_fine_attesa
    incarico.stato = "attivo"
    sincronizza_evento_da_termine(session, incarico, termine)
    registra_storico_termine(session, termine, "completato", "Fine attesa osservazioni confermata")
    ricalcola_termini_incarico(session, incarico, "Fine attesa osservazioni confermata")


def rileva_incongruenze_incarico(incarico) -> list[Incongruenza]:
    risultati: list[Incongruenza] = []
    termini_attivi = [t for t in getattr(incarico, "termini", []) if getattr(t, "attivo", True)]
    eventi = [e for e in getattr(incarico, "eventi", []) if not getattr(e, "annullato", False)]

    per_tipo: dict[str, list] = {}
    for termine in termini_attivi:
        tipo = _tipo_normalizzato(termine.tipo_termine)
        per_tipo.setdefault(tipo, []).append(termine)
        scadenza = calcola_scadenza_termine(incarico, termine)
        if scadenza is None:
            risultati.append(Incongruenza(
                "errore", "termine_non_calcolabile",
                f"Il termine {termine.tipo_termine} non ha una data calcolabile.",
                termine_id=termine.id,
            ))

        collegato = next((e for e in eventi if getattr(e, "termine_id", None) == termine.id), None)
        if tipo in TIPI_SCADENZA_SINCRONIZZABILI and collegato is None:
            risultati.append(Incongruenza(
                "avviso", "evento_collegato_mancante",
                f"Il termine {termine.tipo_termine} non ha ancora un Evento collegato.",
                termine_id=termine.id,
            ))
        elif collegato is not None and (
            _tipo_normalizzato(collegato.tipo) != tipo
            or collegato.data != scadenza
            or bool(collegato.completato) != bool(termine.completato)
        ):
            risultati.append(Incongruenza(
                "errore", "evento_collegato_disallineato",
                f"L'Evento collegato al termine {termine.tipo_termine} non e' allineato.",
                termine_id=termine.id,
                evento_id=collegato.id,
            ))

    for tipo, termini in per_tipo.items():
        if tipo != "personalizzato" and len(termini) > 1:
            risultati.append(Incongruenza(
                "avviso", "termini_duplicati",
                f"Sono presenti {len(termini)} termini attivi di tipo {tipo}.",
            ))

    for evento in eventi:
        tipo = _tipo_normalizzato(evento.tipo)
        if getattr(evento, "termine_id", None) is not None or tipo not in per_tipo:
            continue
        date_termine = {
            calcola_scadenza_termine(incarico, termine)
            for termine in per_tipo[tipo]
            if calcola_scadenza_termine(incarico, termine) is not None
        }
        if evento.data is not None and evento.data not in date_termine:
            risultati.append(Incongruenza(
                "info", "evento_storico_divergente",
                f"L'Evento storico {tipo} del {evento.data:%d/%m/%Y} differisce dal Termine corrente.",
                evento_id=evento.id,
            ))

    sequenza = []
    for tipo in ("bozza", "osservazioni", "deposito"):
        date_tipo = [
            calcola_scadenza_termine(incarico, t)
            for t in per_tipo.get(tipo, [])
            if calcola_scadenza_termine(incarico, t) is not None
        ]
        if date_tipo:
            sequenza.append((tipo, min(date_tipo)))
    for precedente, successivo in zip(sequenza, sequenza[1:]):
        if precedente[1] > successivo[1]:
            risultati.append(Incongruenza(
                "errore", "sequenza_date_non_valida",
                f"La data {successivo[0]} precede la data {precedente[0]}.",
            ))

    return risultati
