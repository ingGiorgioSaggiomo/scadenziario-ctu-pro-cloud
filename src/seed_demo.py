"""Popola il database con dati dimostrativi minimi."""

from datetime import date, timedelta

from src.database import init_db, get_session
from src.models import Incarico, Termine, Evento, Sospensione, Documento


def seed():
    init_db()
    session = get_session()

    # Non rigenerare dati demo se esistono incarichi reali
    real_count = (
        session.query(Incarico)
        .filter(Incarico.origine_dato != "demo")
        .count()
    )
    if real_count > 0:
        print(
            f"Seed annullato: trovati {real_count} incarichi reali nel database. "
            "Per rigenerare i demo elimina prima i dati reali."
        )
        session.close()
        return

    # Incarico CTU
    ctu = Incarico(
        numero_rg="1234/2025",
        tribunale="Tribunale di Roma",
        tipo="CTU",
        giudice="Dott. Rossi",
        parti="Bianchi c/ Verdi",
        oggetto="Accertamento danni da infiltrazione",
        data_conferimento=date(2025, 3, 10),
        data_giuramento=date(2025, 3, 10),
        data_inizio_operazioni=date(2025, 3, 20),
        data_invio_bozza=date(2025, 6, 18),
        stato="attivo",
        origine_dato="demo",
    )

    ctu.termini = [
        Termine(
            tipo_termine="bozza",
            giorni=90,
            decorrenza="data_inizio_operazioni",
            tipo_computo="naturali",
            completato=True,
        ),
        Termine(
            tipo_termine="osservazioni",
            giorni=30,
            decorrenza="data_invio_bozza",
            tipo_computo="naturali",
        ),
        Termine(
            tipo_termine="deposito",
            giorni=30,
            decorrenza="data_scadenza_osservazioni",
            tipo_computo="naturali",
        ),
    ]

    ctu.eventi = [
        Evento(
            tipo="sopralluogo",
            data=date(2025, 4, 5),
            ora="10:00",
            luogo="Via Roma 1, Roma",
            descrizione="Primo accesso immobile",
        ),
    ]

    # Incarico Procura
    procura = Incarico(
        numero_rg="5678/2025",
        tribunale="Procura della Repubblica di Roma",
        tipo="Procura",
        giudice="PM Dott. Neri",
        parti="Proc. Rep. c/ Ignoti",
        oggetto="Accertamento tecnico su struttura",
        data_conferimento=date(2025, 2, 15),
        data_inizio_operazioni=date(2025, 2, 25),
        stato="attivo",
        origine_dato="demo",
    )

    procura.termini = [
        Termine(
            tipo_termine="deposito",
            giorni=60,
            decorrenza="data_inizio_operazioni",
            tipo_computo="naturali",
        ),
    ]

    # Incarico RESA con sospensione feriale
    resa = Incarico(
        numero_rg="9012/2024",
        tribunale="Tribunale di Milano",
        tipo="RESA",
        giudice="Dott.ssa Blu",
        parti="Condominio Alfa c/ Impresa Beta",
        oggetto="Verifica opere eseguite",
        data_conferimento=date(2024, 11, 5),
        data_giuramento=date(2024, 11, 5),
        data_inizio_operazioni=date(2024, 11, 15),
        stato="attivo",
        origine_dato="demo",
    )

    resa.sospensioni = [
        Sospensione(
            data_inizio=date(2025, 8, 1),
            data_fine=date(2025, 8, 31),
            motivo="Sospensione feriale",
        ),
    ]

    resa.termini = [
        Termine(
            tipo_termine="bozza",
            giorni=120,
            decorrenza="data_inizio_operazioni",
            tipo_computo="naturali",
        ),
    ]

    resa.documenti = [
        Documento(
            nome="Verbale giuramento",
            tipo="verbale",
            data_documento=date(2024, 11, 5),
        ),
    ]

    session.add_all([ctu, procura, resa])
    session.commit()
    session.close()
    print("Database popolato con dati dimostrativi.")


if __name__ == "__main__":
    seed()
