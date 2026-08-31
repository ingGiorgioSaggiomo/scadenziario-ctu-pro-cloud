"""Test per aggiornamenti controllati dalla chat."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.chat_updates import (
    aggiungi_nota_incarico_da_chat,
    aggiungi_pagamento_da_chat,
    aggiorna_stato_incarico_da_chat,
    aggiorna_termine_manuale_da_chat,
    anteprima_aggiungi_pagamento,
    trova_incarico,
)
from src.models import Base, Evento, Incarico, ModificaChat, StoricoTermine, Termine
from src.pagamenti import riepilogo_pagamenti


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _incarico(numero_rg="57/2024", parti="Rossi vs Bianchi"):
    return Incarico(
        tipo="CTU",
        numero_rg=numero_rg,
        tribunale="Tribunale di Napoli",
        parti=parti,
        data_conferimento=date(2026, 1, 1),
        stato="attivo",
        priorita="media",
        origine_dato="manuale",
    )


def test_aggiungi_pagamento_da_chat_crea_registro_modifica():
    session = _session()
    inc = _incarico()
    session.add(inc)
    session.commit()

    preview = anteprima_aggiungi_pagamento(session, "57/2024", "acconto", importo_dovuto="1000,00", importo_ricevuto="250,00")
    assert preview["incarico"] == "CTU 57/2024 - Tribunale di Napoli"
    assert "250,00" in preview["dopo"]

    pagamento = aggiungi_pagamento_da_chat(
        session,
        "57/2024",
        "acconto",
        importo_dovuto="1000,00",
        importo_ricevuto="250,00",
        richiesta="registra acconto",
        confermato=True,
        backup=False,
    )

    assert pagamento.id is not None
    riepilogo = riepilogo_pagamenti(inc.pagamenti)
    assert riepilogo["totale_ricevuto"] == 250
    assert session.query(ModificaChat).one().azione == "aggiungi_pagamento"
    session.close()


def test_aggiungi_pagamento_da_chat_calcola_totale_da_imponibile_e_spese():
    session = _session()
    inc = _incarico()
    session.add(inc)
    session.commit()

    pagamento = aggiungi_pagamento_da_chat(
        session,
        "57/2024",
        "saldo",
        imponibile="1000,00",
        spese="150,00",
        importo_ricevuto="0",
        richiesta="registra saldo da decreto",
        confermato=True,
        backup=False,
    )

    assert pagamento.imponibile == 1000
    assert pagamento.spese == 150
    assert pagamento.importo_dovuto == 1192
    riepilogo = riepilogo_pagamenti(inc.pagamenti)
    assert riepilogo["residuo"] == 1192
    session.close()


def test_aggiorna_stato_incarico_da_chat():
    session = _session()
    inc = _incarico()
    session.add(inc)
    session.commit()

    aggiorna_stato_incarico_da_chat(
        session, inc.id, "attesa osservazioni", confermato=True, backup=False
    )

    assert inc.stato == "attesa osservazioni"
    assert session.query(ModificaChat).one().azione == "aggiorna_stato_incarico"
    session.close()


def test_aggiorna_stato_incarico_da_chat_rifiuta_stato_non_valido():
    session = _session()
    inc = _incarico()
    session.add(inc)
    session.commit()

    with pytest.raises(ValueError, match="Stato non valido"):
        aggiorna_stato_incarico_da_chat(
            session, inc.id, "da vedere", confermato=True, backup=False
        )
    session.close()


def test_aggiungi_nota_incarico_da_chat_append_senza_cancellare_note():
    session = _session()
    inc = _incarico()
    inc.note = "nota esistente"
    session.add(inc)
    session.commit()

    aggiungi_nota_incarico_da_chat(
        session, "57/2024", "nuova nota", confermato=True, backup=False
    )

    assert "nota esistente" in inc.note
    assert "nuova nota" in inc.note
    session.close()


def test_aggiorna_termine_manuale_da_chat():
    session = _session()
    inc = _incarico()
    inc.termini = [
        Termine(
            tipo_termine="bozza",
            giorni=30,
            decorrenza="data_conferimento",
            attivo=True,
            completato=False,
        )
    ]
    session.add(inc)
    session.commit()

    termine = aggiorna_termine_manuale_da_chat(
        session,
        "57/2024",
        "bozza",
        "31/07/2026",
        richiesta="proroga confermata",
        confermato=True,
        backup=False,
    )

    assert termine.decorrenza == "data_manual"
    assert termine.giorni == 0
    assert termine.data_manual == date(2026, 7, 31)
    assert termine.data_scadenza == date(2026, 7, 31)
    evento = session.query(Evento).filter(Evento.termine_id == termine.id).one()
    assert evento.data == date(2026, 7, 31)
    assert session.query(StoricoTermine).count() == 2
    assert session.query(ModificaChat).one().azione == "aggiorna_termine_manuale"
    session.close()


def test_modifica_da_chat_richiede_conferma_esplicita():
    session = _session()
    inc = _incarico()
    session.add(inc)
    session.commit()

    with pytest.raises(PermissionError, match="conferma esplicita"):
        aggiungi_nota_incarico_da_chat(session, inc.id, "nota senza conferma", backup=False)

    assert inc.note is None
    assert session.query(ModificaChat).count() == 0
    session.close()


def test_trova_incarico_chiede_id_se_ricerca_ambigua():
    session = _session()
    session.add_all([_incarico("1/2026", "Rossi"), _incarico("2/2026", "Rossi")])
    session.commit()

    with pytest.raises(ValueError, match="Ricerca ambigua"):
        trova_incarico(session, "Rossi")
    session.close()
