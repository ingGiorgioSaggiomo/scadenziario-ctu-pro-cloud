"""Aggiornamenti controllati avviabili dalla chat dopo conferma esplicita."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from src.backup_tools import crea_backup_database
from src.models import Incarico, ModificaChat, Pagamento, Termine
from src.pagamenti import calcola_totale_fattura, fmt_euro, riepilogo_pagamenti
from src.termine_eventi import aggiorna_termine
from src.utils import STATI_INCARICO, TIPI_TERMINE


OPERAZIONI_CHAT_SUPPORTATE = [
    "aggiungi_pagamento",
    "aggiorna_stato_incarico",
    "aggiungi_nota_incarico",
    "aggiorna_termine_manuale",
]


def _verifica_conferma(confermato: bool) -> None:
    if not confermato:
        raise PermissionError(
            "Modifica non eseguita: serve la conferma esplicita dell'utente."
        )


def _normalizza_testo(value: object) -> str:
    return str(value or "").strip().lower()


def _parse_data(value: date | str | None) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    testo = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(testo, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Data non valida: {value}. Usa il formato gg/mm/aaaa.")


def _parse_importo(value: Decimal | int | float | str | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    testo = str(value).strip()
    if "," in testo and "." in testo:
        testo = testo.replace(".", "").replace(",", ".")
    elif "," in testo:
        testo = testo.replace(",", ".")
    try:
        return Decimal(testo).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Importo non valido: {value}.") from exc


def _label_incarico(incarico: Incarico) -> str:
    return f"{incarico.tipo} {incarico.numero_rg} - {incarico.tribunale}"


def _riepilogo_testuale(incarico: Incarico) -> str:
    riepilogo = riepilogo_pagamenti(incarico.pagamenti)
    return (
        f"{_label_incarico(incarico)} | stato={incarico.stato} | "
        f"dovuto={fmt_euro(riepilogo['totale_dovuto'])} | "
        f"ricevuto={fmt_euro(riepilogo['totale_ricevuto'])} | "
        f"residuo={fmt_euro(riepilogo['residuo'])}"
    )


def trova_incarico(session, query: str | int) -> Incarico:
    """Trova un incarico con ricerca prudente, evitando aggiornamenti ambigui."""
    if isinstance(query, int) or str(query).strip().isdigit():
        incarico = session.get(Incarico, int(query))
        if incarico:
            return incarico

    needle = _normalizza_testo(query)
    if not needle:
        raise ValueError("Indica quale incarico vuoi aggiornare.")

    incarichi = session.query(Incarico).order_by(Incarico.id).all()
    exact = [
        inc for inc in incarichi
        if needle in {
            _normalizza_testo(inc.numero_rg),
            _normalizza_testo(f"{inc.tipo} {inc.numero_rg}"),
            _normalizza_testo(_label_incarico(inc)),
        }
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError("Ho trovato piu incarichi uguali: serve l'ID dell'incarico.")

    matches = []
    for inc in incarichi:
        haystack = " ".join(
            _normalizza_testo(part)
            for part in [inc.tipo, inc.numero_rg, inc.tribunale, inc.giudice, inc.parti, inc.oggetto, inc.note]
        )
        if needle in haystack:
            matches.append(inc)

    if not matches:
        raise ValueError(f"Nessun incarico trovato per: {query}.")
    if len(matches) > 1:
        elenco = "; ".join(f"ID {inc.id}: {_label_incarico(inc)}" for inc in matches[:5])
        raise ValueError(f"Ricerca ambigua. Specifica l'ID. Corrispondenze: {elenco}")
    return matches[0]


def _registra_modifica(session, incarico: Incarico | None, azione: str, richiesta: str | None, prima: str, dopo: str, note: str | None = None) -> None:
    session.add(
        ModificaChat(
            incarico_id=incarico.id if incarico else None,
            azione=azione,
            richiesta=richiesta,
            prima=prima,
            dopo=dopo,
            note=note,
        )
    )


def anteprima_aggiungi_pagamento(
    session,
    incarico_query: str | int,
    tipo: str,
    importo_dovuto: Decimal | int | float | str | None = None,
    importo_ricevuto: Decimal | int | float | str | None = None,
    imponibile: Decimal | int | float | str | None = None,
    spese: Decimal | int | float | str | None = None,
) -> dict[str, str]:
    incarico = trova_incarico(session, incarico_query)
    imponibile_value = _parse_importo(imponibile)
    spese_value = _parse_importo(spese)
    calcolo = calcola_totale_fattura(imponibile_value, spese_value)
    dovuto = calcolo["totale"] if imponibile_value or spese_value else _parse_importo(importo_dovuto)
    ricevuto = _parse_importo(importo_ricevuto)
    prima = riepilogo_pagamenti(incarico.pagamenti)
    provvisorio = list(incarico.pagamenti) + [
        Pagamento(
            tipo=tipo,
            imponibile=imponibile_value,
            spese=spese_value,
            importo_dovuto=dovuto,
            importo_ricevuto=ricevuto,
        )
    ]
    dopo = riepilogo_pagamenti(provvisorio)
    return {
        "incarico": _label_incarico(incarico),
        "prima": f"ricevuto {fmt_euro(prima['totale_ricevuto'])}, residuo {fmt_euro(prima['residuo'])}",
        "dopo": f"ricevuto {fmt_euro(dopo['totale_ricevuto'])}, residuo {fmt_euro(dopo['residuo'])}",
    }


def aggiungi_pagamento_da_chat(
    session,
    incarico_query: str | int,
    tipo: str,
    importo_dovuto: Decimal | int | float | str | None = None,
    importo_ricevuto: Decimal | int | float | str | None = None,
    imponibile: Decimal | int | float | str | None = None,
    spese: Decimal | int | float | str | None = None,
    data_riferimento: date | str | None = None,
    data_pagamento: date | str | None = None,
    pagatore: str | None = None,
    descrizione: str | None = None,
    note: str | None = None,
    richiesta: str | None = None,
    confermato: bool = False,
    backup: bool = True,
) -> Pagamento:
    _verifica_conferma(confermato)
    if tipo not in {"acconto", "saldo", "altro"}:
        raise ValueError("Tipo pagamento non valido. Usa acconto, saldo oppure altro.")
    incarico = trova_incarico(session, incarico_query)
    prima = _riepilogo_testuale(incarico)
    imponibile_value = _parse_importo(imponibile)
    spese_value = _parse_importo(spese)
    calcolo = calcola_totale_fattura(imponibile_value, spese_value)
    if backup:
        crea_backup_database("prima_chat_aggiungi_pagamento")
    pagamento = Pagamento(
        tipo=tipo,
        imponibile=imponibile_value,
        spese=spese_value,
        importo_dovuto=calcolo["totale"] if imponibile_value or spese_value else _parse_importo(importo_dovuto),
        importo_ricevuto=_parse_importo(importo_ricevuto),
        data_riferimento=_parse_data(data_riferimento),
        data_pagamento=_parse_data(data_pagamento),
        pagatore=pagatore,
        descrizione=descrizione,
        note=note,
    )
    try:
        incarico.pagamenti.append(pagamento)
        session.flush()
        dopo = _riepilogo_testuale(incarico)
        _registra_modifica(session, incarico, "aggiungi_pagamento", richiesta, prima, dopo, note)
        session.commit()
        return pagamento
    except Exception:
        session.rollback()
        raise


def aggiorna_stato_incarico_da_chat(
    session,
    incarico_query: str | int,
    nuovo_stato: str,
    richiesta: str | None = None,
    confermato: bool = False,
    backup: bool = True,
) -> Incarico:
    _verifica_conferma(confermato)
    if nuovo_stato not in STATI_INCARICO:
        raise ValueError(f"Stato non valido. Stati ammessi: {', '.join(STATI_INCARICO)}.")
    incarico = trova_incarico(session, incarico_query)
    prima = f"stato={incarico.stato}"
    if backup:
        crea_backup_database("prima_chat_aggiorna_stato")
    try:
        incarico.stato = nuovo_stato
        dopo = f"stato={incarico.stato}"
        _registra_modifica(session, incarico, "aggiorna_stato_incarico", richiesta, prima, dopo)
        session.commit()
        return incarico
    except Exception:
        session.rollback()
        raise


def aggiungi_nota_incarico_da_chat(
    session,
    incarico_query: str | int,
    nota: str,
    richiesta: str | None = None,
    confermato: bool = False,
    backup: bool = True,
) -> Incarico:
    _verifica_conferma(confermato)
    testo = str(nota or "").strip()
    if not testo:
        raise ValueError("La nota non puo essere vuota.")
    incarico = trova_incarico(session, incarico_query)
    prima = incarico.note or ""
    if backup:
        crea_backup_database("prima_chat_aggiungi_nota")
    try:
        prefisso = date.today().strftime("%d/%m/%Y")
        incarico.note = f"{prima}\n{prefisso} - {testo}".strip() if prima else f"{prefisso} - {testo}"
        _registra_modifica(session, incarico, "aggiungi_nota_incarico", richiesta, prima, incarico.note)
        session.commit()
        return incarico
    except Exception:
        session.rollback()
        raise


def aggiorna_termine_manuale_da_chat(
    session,
    incarico_query: str | int,
    tipo_termine: str,
    nuova_data: date | str,
    richiesta: str | None = None,
    confermato: bool = False,
    backup: bool = True,
) -> Termine:
    _verifica_conferma(confermato)
    if tipo_termine not in TIPI_TERMINE:
        raise ValueError(f"Tipo termine non valido. Tipi ammessi: {', '.join(TIPI_TERMINE)}.")
    incarico = trova_incarico(session, incarico_query)
    candidati = [
        termine for termine in incarico.termini
        if termine.tipo_termine == tipo_termine and termine.attivo and not termine.completato
    ]
    if not candidati:
        raise ValueError(f"Nessun termine attivo di tipo {tipo_termine} trovato per questo incarico.")
    if len(candidati) > 1:
        ids = ", ".join(str(termine.id) for termine in candidati)
        raise ValueError(f"Ci sono piu termini {tipo_termine} attivi: serve scegliere l'ID ({ids}).")
    termine = candidati[0]
    data = _parse_data(nuova_data)
    prima = (
        f"termine_id={termine.id}; tipo={termine.tipo_termine}; "
        f"decorrenza={termine.decorrenza}; giorni={termine.giorni}; "
        f"data_manual={termine.data_manual}; data_scadenza={termine.data_scadenza}"
    )
    if backup:
        crea_backup_database("prima_chat_aggiorna_termine")
    try:
        aggiorna_termine(
            session,
            incarico,
            termine,
            tipo_termine=termine.tipo_termine,
            giorni=0,
            decorrenza="data_manual",
            data_manual=data,
            attivo=termine.attivo,
            completato=termine.completato,
            prorogato=termine.prorogato,
            note=termine.note,
            motivo=richiesta or "Aggiornamento manuale richiesto dalla chat",
        )
        dopo = (
            f"termine_id={termine.id}; tipo={termine.tipo_termine}; "
            f"decorrenza={termine.decorrenza}; giorni={termine.giorni}; "
            f"data_manual={termine.data_manual}; data_scadenza={termine.data_scadenza}"
        )
        _registra_modifica(session, incarico, "aggiorna_termine_manuale", richiesta, prima, dopo)
        session.commit()
        return termine
    except Exception:
        session.rollback()
        raise
