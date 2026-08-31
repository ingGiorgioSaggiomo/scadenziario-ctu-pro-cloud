from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, Evento, Incarico, StoricoTermine, Termine
from src.termine_eventi import (
    aggiorna_termine,
    completa_bozza,
    completa_osservazioni,
    rileva_incongruenze_incarico,
    sincronizza_evento_da_termine,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _incarico(session):
    inc = Incarico(
        numero_rg="1/2026",
        tribunale="Tribunale",
        tipo="CTU",
        data_conferimento=date(2026, 1, 1),
        stato="attivo",
    )
    session.add(inc)
    session.flush()
    return inc


def test_sincronizzazione_crea_e_aggiorna_un_solo_evento_collegato():
    session = _session()
    inc = _incarico(session)
    termine = Termine(
        incarico_id=inc.id,
        tipo_termine="deposito",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2026, 9, 14),
        attivo=True,
    )
    session.add(termine)
    session.flush()

    evento = sincronizza_evento_da_termine(session, inc, termine)
    session.flush()
    assert evento.termine_id == termine.id
    assert evento.data == date(2026, 9, 14)

    termine.data_manual = date(2026, 9, 20)
    secondo = sincronizza_evento_da_termine(session, inc, termine)
    session.flush()
    assert secondo.id == evento.id
    assert secondo.data == date(2026, 9, 20)
    assert session.query(Evento).count() == 1


def test_modifica_termine_aggiorna_evento_e_registra_storico():
    session = _session()
    inc = _incarico(session)
    termine = Termine(
        incarico_id=inc.id,
        tipo_termine="deposito",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2026, 8, 31),
        data_scadenza=date(2026, 8, 31),
        attivo=True,
    )
    session.add(termine)
    session.flush()
    sincronizza_evento_da_termine(session, inc, termine)

    aggiorna_termine(
        session,
        inc,
        termine,
        tipo_termine="deposito",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2026, 9, 14),
        attivo=True,
        completato=False,
        prorogato=True,
        note="Proroga",
        motivo="Proroga del Tribunale",
    )
    session.flush()

    assert termine.data_scadenza == date(2026, 9, 14)
    assert termine.evento_collegato.data == date(2026, 9, 14)
    storico = session.query(StoricoTermine).order_by(StoricoTermine.id).all()
    assert [voce.azione for voce in storico] == ["prima_modifica", "dopo_modifica"]
    assert storico[0].data_scadenza == date(2026, 8, 31)
    assert storico[1].data_scadenza == date(2026, 9, 14)


def test_workflow_bozza_e_osservazioni_aggiorna_stato_e_date():
    session = _session()
    inc = _incarico(session)
    bozza = Termine(
        incarico_id=inc.id,
        tipo_termine="bozza",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2026, 7, 10),
        attivo=True,
    )
    osservazioni = Termine(
        incarico_id=inc.id,
        tipo_termine="osservazioni",
        giorni=20,
        decorrenza="data_invio_bozza",
        attivo=True,
    )
    deposito = Termine(
        incarico_id=inc.id,
        tipo_termine="deposito",
        giorni=10,
        decorrenza="data_ricezione_osservazioni",
        attivo=True,
    )
    session.add_all([bozza, osservazioni, deposito])
    session.flush()

    completa_bozza(session, inc, bozza, date(2026, 7, 5))
    assert bozza.completato is True
    assert inc.data_invio_bozza == date(2026, 7, 5)
    assert inc.stato == "attesa osservazioni"
    assert osservazioni.data_scadenza == date(2026, 7, 25)
    assert osservazioni.evento_collegato.data == date(2026, 7, 25)

    completa_osservazioni(session, inc, osservazioni, date(2026, 7, 25))
    assert osservazioni.completato is True
    assert inc.data_ricezione_osservazioni == date(2026, 7, 25)
    assert inc.stato == "attivo"
    assert deposito.data_scadenza == date(2026, 8, 4)
    assert deposito.evento_collegato.data == date(2026, 8, 4)


def test_controllo_rileva_evento_disallineato_e_sequenza_errata():
    session = _session()
    inc = _incarico(session)
    bozza = Termine(
        incarico_id=inc.id,
        tipo_termine="bozza",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2026, 9, 20),
        attivo=True,
    )
    deposito = Termine(
        incarico_id=inc.id,
        tipo_termine="deposito",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2026, 9, 14),
        attivo=True,
    )
    session.add_all([bozza, deposito])
    session.flush()
    evento = sincronizza_evento_da_termine(session, inc, deposito)
    session.flush()
    evento.data = date(2026, 8, 31)

    codici = {voce.codice for voce in rileva_incongruenze_incarico(inc)}
    assert "evento_collegato_mancante" in codici
    assert "evento_collegato_disallineato" in codici
    assert "sequenza_date_non_valida" in codici
