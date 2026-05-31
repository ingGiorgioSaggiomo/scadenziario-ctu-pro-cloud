# Deploy online di Scadenziario CTU Pro

## Scelta consigliata

Per dati CTU e procedure con informazioni personali, evita un deploy pubblico senza controllo forte degli accessi.
La strada consigliata e':

1. servizio cloud con HTTPS;
2. database PostgreSQL gestito;
3. password di accesso impostata come segreto;
4. backup automatici del database;
5. repository senza file `.db`, Excel reali, backup o segreti.

Streamlit Community Cloud e' semplice, ma non e' la scelta migliore per questo caso:
lo storage locale non e' persistente e i termini del servizio non sono pensati per trattare dati personali sensibili.

## Variabili/secret necessari

Imposta sempre questi valori nel provider cloud:

```toml
SUPABASE_DB_PASSWORD = "password-del-database-supabase"
ACCESS_PASSWORD = "una-password-lunga-e-unica"
```

In locale puoi continuare senza password e con SQLite. Online, se `DATABASE_URL` e' impostato,
l'app si blocca se manca `ACCESS_PASSWORD`.

## Deploy con Docker

Il repository contiene un `Dockerfile` pronto per qualunque provider che supporta container.
Il container espone Streamlit sulla porta definita da `PORT`, oppure `8501` in assenza di `PORT`.

Comando locale di prova:

```bash
docker build -t scadenziario-ctu-pro .
docker run --rm -p 8501:8501 ^
  -e ACCESS_PASSWORD="password-lunga" ^
  -e DATABASE_URL="postgresql://utente:password@host:5432/database" ^
  scadenziario-ctu-pro
```

## Esempio Render

Il file `render.yaml.example` e' un esempio di Blueprint Render.
Rinominalo in `render.yaml` solo quando vuoi creare le risorse.

Prima di usarlo controlla:

- piano e costi;
- regione del database;
- policy privacy;
- backup del database;
- password di accesso.

## Migrazione dei dati SQLite esistenti

Quando PostgreSQL online e' pronto, puoi migrare il database locale con:

```bash
set DATABASE_URL=postgresql://utente:password@host:5432/database
python scripts/migrate_sqlite_to_postgres.py --sqlite data/scadenziario.db
```

Per svuotare prima il database remoto:

```bash
python scripts/migrate_sqlite_to_postgres.py --sqlite data/scadenziario.db --replace
```

Non eseguire `--replace` se nel database online ci sono dati da conservare.

## Pulizia Git

Non committare mai:

- `data/*.db`;
- file Excel reali;
- cartelle `backup_*`;
- `.streamlit/secrets.toml`;
- `.env`.

Se un database reale e' gia' stato caricato su GitHub, considera il repository compromesso:
crea un nuovo repository privato pulito oppure riscrivi la history e cambia eventuali password.
