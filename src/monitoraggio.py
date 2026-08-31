"""Riepilogo operativo condiviso tra app, script e controllo Codex."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import selectinload

from src.models import Incarico
from src.pagamenti import fmt_euro, riepilogo_pagamenti
from src.termine_eventi import rileva_incongruenze_incarico
from src.utils import (
    attesa_osservazioni_da_mostrare_dashboard,
    classifica_per_dashboard,
    scadenza_osservazioni_dashboard,
    trova_prossima_attivita_dashboard,
)


PRIORITA_CATEGORIA = {
    "scaduto": 0,
    "riattivare": 0,
    "critico": 1,
    "urgente": 2,
    "pianificare": 3,
    "dati_mancanti": 4,
    "anomalia": 5,
    "pagamento": 6,
}


@dataclass(frozen=True)
class VoceMonitoraggio:
    categoria: str
    incarico_id: int
    incarico: str
    attivita: str
    data: Optional[date]
    giorni: Optional[int]
    azione: str
    dettaglio: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def etichetta_fonte_database() -> str:
    from src.database import engine

    if engine.name == "postgresql":
        return "Supabase/PostgreSQL"
    if engine.name == "sqlite":
        return "SQLite locale"
    return engine.name


def _label_incarico(incarico: Incarico) -> str:
    return f"{incarico.tipo} {incarico.numero_rg} - {incarico.tribunale}"


def _azione_scadenza(alert: str, tipo: str) -> str:
    if alert == "scaduto":
        return f"Verificare subito e completare o aggiornare la scadenza {tipo}."
    if alert == "critico":
        return f"Dare priorita immediata all'attivita {tipo}."
    if alert == "urgente":
        return f"Programmare il lavoro su {tipo} entro pochi giorni."
    if alert == "pianificare":
        return f"Inserire l'attivita {tipo} nella pianificazione del mese."
    return "Definire una scadenza o un evento operativo valido."


def genera_voci_monitoraggio(session, data_oggi: Optional[date] = None) -> list[VoceMonitoraggio]:
    """Genera le sole voci che richiedono attenzione o controllo."""
    oggi = data_oggi or date.today()
    incarichi = (
        session.query(Incarico)
        .options(
            selectinload(Incarico.termini),
            selectinload(Incarico.eventi),
            selectinload(Incarico.sospensioni),
            selectinload(Incarico.pagamenti),
        )
        .order_by(Incarico.id)
        .all()
    )
    voci: list[VoceMonitoraggio] = []

    for incarico in incarichi:
        label = _label_incarico(incarico)
        stato = str(incarico.stato or "").strip().lower()

        if stato == "attesa osservazioni":
            scadenza = scadenza_osservazioni_dashboard(incarico)
            if scadenza is None:
                voci.append(VoceMonitoraggio(
                    "dati_mancanti",
                    incarico.id,
                    label,
                    "osservazioni",
                    None,
                    None,
                    "Definire la scadenza delle osservazioni.",
                ))
            elif attesa_osservazioni_da_mostrare_dashboard(incarico, oggi):
                giorni = (scadenza - oggi).days
                voci.append(VoceMonitoraggio(
                    "riattivare",
                    incarico.id,
                    label,
                    "fine attesa osservazioni",
                    scadenza,
                    giorni,
                    "Concludere l'attesa e riportare l'incarico allo stato attivo per il deposito.",
                ))
        elif stato == "attivo":
            prossima = trova_prossima_attivita_dashboard(incarico, oggi)
            alert = classifica_per_dashboard(incarico.stato, prossima)
            if alert in {"scaduto", "critico", "urgente", "pianificare", "dati_mancanti"}:
                tipo = prossima.tipo_termine if prossima else "da definire"
                voci.append(VoceMonitoraggio(
                    alert,
                    incarico.id,
                    label,
                    tipo,
                    prossima.data_scadenza if prossima else None,
                    prossima.giorni_residui if prossima else None,
                    _azione_scadenza(alert, tipo),
                ))
        elif stato in {"sospeso", "chiuso"}:
            errori = [
                voce for voce in rileva_incongruenze_incarico(incarico)
                if voce.livello == "errore"
            ]
            if errori:
                voci.append(VoceMonitoraggio(
                    "anomalia",
                    incarico.id,
                    label,
                    f"controllo incarico {stato}",
                    None,
                    None,
                    "Verificare la coerenza di Termini ed Eventi.",
                    "; ".join(voce.descrizione for voce in errori[:3]),
                ))

        pagamenti = riepilogo_pagamenti(incarico.pagamenti)
        residuo = Decimal(pagamenti["residuo"])
        if residuo > 0:
            voci.append(VoceMonitoraggio(
                "pagamento",
                incarico.id,
                label,
                "residuo da incassare",
                None,
                None,
                "Verificare lo stato del pagamento ed effettuare eventuale sollecito.",
                f"Residuo: {fmt_euro(residuo)} euro",
            ))

    return sorted(
        voci,
        key=lambda voce: (
            PRIORITA_CATEGORIA.get(voce.categoria, 99),
            voce.giorni if voce.giorni is not None else 999999,
            voce.incarico.lower(),
        ),
    )


def formatta_riepilogo_operativo(
    voci: list[VoceMonitoraggio],
    data_oggi: Optional[date] = None,
    fonte: Optional[str] = None,
) -> str:
    oggi = data_oggi or date.today()
    righe = [
        f"Controllo Scadenziario CTU Pro del {oggi:%d/%m/%Y}",
        f"Fonte dati: {fonte or etichetta_fonte_database()}",
    ]
    if not voci:
        righe.append("Nessuna scadenza o anomalia operativa da segnalare.")
        return "\n".join(righe)

    for voce in voci:
        data_testo = voce.data.strftime("%d/%m/%Y") if voce.data else "-"
        giorni_testo = str(voce.giorni) if voce.giorni is not None else "-"
        dettaglio = f" | {voce.dettaglio}" if voce.dettaglio else ""
        righe.append(
            f"[{voce.categoria.upper()}] {voce.incarico} | {voce.attivita} | "
            f"data {data_testo} | gg {giorni_testo} | {voce.azione}{dettaglio}"
        )
    return "\n".join(righe)
