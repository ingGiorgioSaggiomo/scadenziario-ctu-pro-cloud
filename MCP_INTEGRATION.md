# Integrazione MCP — Scadenziario CTU Pro

## Obiettivo

Esporre a ChatGPT, in sola lettura, le informazioni operative dello Scadenziario CTU Pro per briefing settimanali e controlli incrociati con calendario ed e-mail.

Il database dello Scadenziario resta la fonte primaria delle scadenze. Il server MCP non modifica incarichi, termini, eventi o documenti.

## Tool esposti

- `active_assignments()` — incarichi attivi;
- `upcoming_deadlines(days=14)` — termini attivi e non completati in scadenza;
- `deadlines_between(start_date, end_date, include_completed=False)` — termini in un intervallo;
- `overdue_deadlines()` — termini scaduti e non completati;
- `upcoming_events(days=14)` — udienze, sopralluoghi, riunioni, depositi e altri eventi;
- `events_between(start_date, end_date, include_completed=False)` — eventi in un intervallo;
- `search_assignment(query)` — ricerca per RG, parti, oggetto o tribunale.

## Avvio locale di sviluppo

```bash
pip install -r requirements.txt
python mcp_server.py
```

Il server usa la stessa configurazione database dell'applicazione (`DATABASE_URL` / PostgreSQL oppure SQLite locale).

## Produzione

Per ChatGPT il server MCP deve essere raggiungibile via HTTPS. Non esporre direttamente il database e non inserire credenziali nel repository.

In produzione:

1. usare lo stesso `DATABASE_URL` PostgreSQL dell'applicazione;
2. eseguire `mcp_server.py` come servizio separato;
3. pubblicarlo dietro HTTPS;
4. aggiungere autenticazione prima di collegarlo a dati CTU reali;
5. mantenere i tool MCP read-only;
6. verificare backup, logging e policy privacy del provider.

## Briefing del lunedì

Flusso previsto:

1. leggere termini scaduti;
2. leggere termini dei successivi 14 giorni;
3. leggere eventi dei successivi 14 giorni;
4. confrontare con Google Calendar;
5. cercare in Gmail comunicazioni recenti pertinenti agli incarichi;
6. evidenziare conflitti, termini mancanti/incoerenti e follow-up;
7. produrre azioni ordinate per urgenza e impatto.

## Sicurezza

Questa prima integrazione non espone funzioni di creazione, modifica o cancellazione. Eventuali funzioni di scrittura dovranno essere progettate separatamente e richiedere conferma esplicita dell'utente.
