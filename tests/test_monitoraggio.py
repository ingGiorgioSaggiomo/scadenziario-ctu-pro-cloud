"""Test del riepilogo operativo condiviso."""

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, Incarico, Pagamento, Termine
from src.monitoraggio import formatta_riepilogo_operativo, genera_voci_monitoraggio


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _incarico(numero: str, stato: str = "attivo") -> Incarico:
    return Incarico(
        tipo="CTU",
        numero_rg=numero,
        tribunale="Tribunale di Napoli",
        data_conferimento=date(2026, 1, 1),
        stato=stato,
        priorita="media",
        origine_dato="manuale",
    )


def test_monitoraggio_segnala_scadenza_e_attesa_da_riattivare():
    session = _session()
    scaduto = _incarico("1/2026")
    scaduto.termini = [Termine(
        tipo_termine="deposito",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2026, 8, 20),
        attivo=True,
    )]
    attesa = _incarico("2/2026", "attesa osservazioni")
    attesa.termini = [
        Termine(
            tipo_termine="osservazioni",
            giorni=0,
            decorrenza="data_manual",
            data_manual=date(2026, 8, 25),
            attivo=True,
        ),
        Termine(
            tipo_termine="deposito",
            giorni=0,
            decorrenza="data_manual",
            data_manual=date(2026, 9, 10),
            attivo=True,
        ),
    ]
    session.add_all([scaduto, attesa])
    session.commit()

    voci = genera_voci_monitoraggio(session, date(2026, 8, 31))

    assert [(voce.incarico_id, voce.categoria) for voce in voci] == [
        (scaduto.id, "scaduto"),
        (attesa.id, "riattivare"),
    ]
    assert voci[1].attivita == "fine attesa osservazioni"
    session.close()


def test_monitoraggio_segnala_residuo_pagamento_e_ignora_regolare():
    session = _session()
    incarico = _incarico("3/2026")
    incarico.termini = [Termine(
        tipo_termine="deposito",
        giorni=0,
        decorrenza="data_manual",
        data_manual=date(2027, 1, 31),
        attivo=True,
    )]
    incarico.pagamenti = [Pagamento(
        tipo="saldo",
        importo_dovuto=1000,
        importo_ricevuto=250,
    )]
    session.add(incarico)
    session.commit()

    voci = genera_voci_monitoraggio(session, date(2026, 8, 31))

    assert len(voci) == 1
    assert voci[0].categoria == "pagamento"
    assert "750,00" in voci[0].dettaglio
    testo = formatta_riepilogo_operativo(voci, date(2026, 8, 31), "Supabase/PostgreSQL")
    assert "Fonte dati: Supabase/PostgreSQL" in testo
    assert "CTU 3/2026" in testo
    session.close()
