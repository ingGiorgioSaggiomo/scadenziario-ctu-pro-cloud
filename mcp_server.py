from __future__ import annotations

from datetime import date

from mcp.server.fastmcp import FastMCP

from src.database import init_db
from src.mcp_queries import (
    find_assignment,
    get_active_assignments,
    get_deadlines,
    get_events,
    get_overdue_deadlines,
    get_upcoming_deadlines,
    get_upcoming_events,
)

mcp = FastMCP(
    "Scadenziario CTU Pro",
    instructions=(
        "Read-only access to CTU and forensic-engineering assignments, deadlines and events. "
        "Use these tools to build operational briefings and cross-check deadlines. "
        "Never infer that a deadline is completed unless the database marks it completed."
    ),
)


@mcp.tool()
def active_assignments():
    """Return all active CTU/forensic-engineering assignments."""
    return get_active_assignments()


@mcp.tool()
def upcoming_deadlines(days: int = 14):
    """Return incomplete active deadlines due in the next N days."""
    return get_upcoming_deadlines(days)


@mcp.tool()
def deadlines_between(start_date: str, end_date: str, include_completed: bool = False):
    """Return deadlines in an inclusive ISO date interval (YYYY-MM-DD)."""
    return get_deadlines(date.fromisoformat(start_date), date.fromisoformat(end_date), include_completed)


@mcp.tool()
def overdue_deadlines():
    """Return active incomplete deadlines whose due date has already passed."""
    return get_overdue_deadlines()


@mcp.tool()
def upcoming_events(days: int = 14):
    """Return upcoming hearings, inspections, meetings, filings and other scheduled events."""
    return get_upcoming_events(days)


@mcp.tool()
def events_between(start_date: str, end_date: str, include_completed: bool = False):
    """Return scheduled events in an inclusive ISO date interval (YYYY-MM-DD)."""
    return get_events(date.fromisoformat(start_date), date.fromisoformat(end_date), include_completed)


@mcp.tool()
def search_assignment(query: str):
    """Search assignments by RG number, parties, subject or court."""
    return find_assignment(query)


if __name__ == "__main__":
    init_db()
    mcp.run(transport="streamable-http")
