# Scadenziario CTU Pro

Applicazione locale per la gestione automatica delle scadenze di incarichi CTU, Procura, RESA, ordini a fare e incarichi tecnici.

## Stack

- Python 3.12
- Streamlit (interfaccia)
- SQLite + SQLAlchemy (database)
- Pandas / OpenPyXL (import/export)
- icalendar (esportazione ICS)

## Installazione

```bash
cd scadenziario-ctu-pro
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

## Avvio

```bash
# Popolare il database con dati dimostrativi
python -m src.seed_demo

# Avviare l'interfaccia
streamlit run app.py
```

## Test

```bash
pytest tests/
```

## Uso online

Per l'uso da smartphone fuori dalla rete locale, usa un deploy cloud con PostgreSQL e password di accesso.
Il progetto e' predisposto per:

- `DATABASE_URL` verso PostgreSQL;
- `ACCESS_PASSWORD` come segreto;
- Dockerfile per hosting cloud;
- migrazione SQLite -> PostgreSQL.

Leggi [DEPLOY_ONLINE.md](DEPLOY_ONLINE.md) prima di pubblicare dati reali.

## Struttura

```
app.py                  # Entry point Streamlit
data/scadenziario.db   # Database SQLite (generato automaticamente)
DEPLOY_ONLINE.md        # Istruzioni deploy cloud sicuro
Dockerfile              # Container per hosting online
scripts/
  migrate_sqlite_to_postgres.py  # Migrazione dati locali verso PostgreSQL
src/
  database.py          # Connessione e sessione DB
  models.py            # Modelli SQLAlchemy
  deadline_engine.py   # Motore calcolo scadenze
  import_excel.py      # Import da Excel
  export_tools.py      # Export Excel / ICS
  seed_demo.py         # Dati dimostrativi
  utils.py             # Utility comuni
tests/
  test_deadline_engine.py
```
