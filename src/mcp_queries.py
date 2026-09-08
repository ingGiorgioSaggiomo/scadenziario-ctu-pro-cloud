from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import get_session
from src.models import Evento, Incarico, Termine


def _iso(value):
    return value.isoformat() if value else None


def _incarico_payload(incarico: Incarico) -> dict[str, Any]:
    return {
        "id": incarico.id,
        "numero_rg": incarico.numero_rg,
        "tribunale": incarico.tribunale,
        "tipo": incarico.tipo,
        "giudice": incarico.giudice,
        "parti": incarico.parti,
        "oggetto": incarico.oggetto,
        "stato": incarico.stato,
        "priorita": incarico.priorita,
        "data_conferimento": _iso(incarico.data_conferimento),
        "data_giuramento": _iso(incarico.data_giuramento),
        "data_inizio_operazioni": _iso(incarico.data_inizio_operazioni),
        "data_invio_bozza": _iso(incarico.data_invio_bozza),
        "data_ricezione_osservazioni": _iso(incarico.data_ricezione_osservazioni),
        "note": incarico.note,
    }


def get_active_assignments() -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.scalars(
            select(Incarico)
            .where(Incarico.stato == "attivo")
            .order_by(Incarico.priorita, Incarico.numero_rg)
        ).all()
        return [_incarico_payload(row) for row in rows]


def get_deadlines(start_date: date, end_date: date, include_completed: bool = False) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = (
            select(Termine)
            .options(selectinload(Termine.incarico))
            .where(
                Termine.attivo.is_(True),
                Termine.data_scadenza.is_not(None),
                Termine.data_scadenza >= start_date,
                Termine.data_scadenza <= end_date,
            )
            .order_by(Termine.data_scadenza.asc())
        )
        if not include_completed:
            stmt = stmt.where(Termine.completato.is_(False))
        rows = session.scalars(stmt).all()
        return [
            {
                "termine_id": row.id,
                "tipo_termine": row.tipo_termine,
                "data_scadenza": _iso(row.data_scadenza),
                "completato": row.completato,
                "prorogato": row.prorogato,
                "note": row.note,
                "incarico": _incarico_payload(row.incarico),
            }
            for row in rows
        ]


def get_upcoming_deadlines(days: int = 14) -> list[dict[str, Any]]:
    days = max(0, min(days, 365))
    today = date.today()
    return get_deadlines(today, today + timedelta(days=days))


def get_overdue_deadlines() -> list[dict[str, Any]]:
    today = date.today()
    with get_session() as session:
        rows = session.scalars(
            select(Termine)
            .options(selectinload(Termine.incarico))
            .where(
                Termine.attivo.is_(True),
                Termine.completato.is_(False),
                Termine.data_scadenza.is_not(None),
                Termine.data_scadenza < today,
            )
            .order_by(Termine.data_scadenza.asc())
        ).all()
        return [
            {
                "termine_id": row.id,
                "tipo_termine": row.tipo_termine,
                "data_scadenza": _iso(row.data_scadenza),
                "giorni_scaduti": (today - row.data_scadenza).days,
                "note": row.note,
                "incarico": _incarico_payload(row.incarico),
            }
            for row in rows
        ]


def get_events(start_date: date, end_date: date, include_completed: bool = False) -> list[dict[str, Any]]:
    with get_session() as session:
        stmt = (
            select(Evento)
            .options(selectinload(Evento.incarico))
            .where(
                Evento.annullato.is_(False),
                Evento.data.is_not(None),
                Evento.data >= start_date,
                Evento.data <= end_date,
            )
            .order_by(Evento.data.asc(), Evento.ora.asc())
        )
        if not include_completed:
            stmt = stmt.where(Evento.completato.is_(False))
        rows = session.scalars(stmt).all()
        return [
            {
                "evento_id": row.id,
                "tipo": row.tipo,
                "data": _iso(row.data),
                "ora": row.ora,
                "luogo": row.luogo,
                "descrizione": row.descrizione,
                "completato": row.completato,
                "incarico": _incarico_payload(row.incarico),
            }
            for row in rows
        ]


def get_upcoming_events(days: int = 14) -> list[dict[str, Any]]:
    days = max(0, min(days, 365))
    today = date.today()
    return get_events(today, today + timedelta(days=days))


def find_assignment(query: str) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    pattern = f"%{query}%"
    with get_session() as session:
        rows = session.scalars(
            select(Incarico)
            .where(
                (Incarico.numero_rg.ilike(pattern))
                | (Incarico.parti.ilike(pattern))
                | (Incarico.oggetto.ilike(pattern))
                | (Incarico.tribunale.ilike(pattern))
            )
            .order_by(Incarico.numero_rg)
        ).all()
        return [_incarico_payload(row) for row in rows]
