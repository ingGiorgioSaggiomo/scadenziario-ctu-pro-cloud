"""Test per l'import Excel."""

from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.database import init_db, get_session
from src.import_excel import _parse_descrizione, importa_excel
from src.models import Evento, Incarico, Sospensione


HEADER = [
    "descrizione", "nomina", "giuramento", "inizio op.",
    "bozza", "osservazioni", "deposito", "udienza",
    "stato", "gg scad.", "note", "sospensione", "ripresa", "gg sosp.",
]


@pytest.fixture(autouse=True)
def _setup(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    new_engine = create_engine(f"sqlite:///{test_db}")
    monkeypatch.setattr("src.database.engine", new_engine)
    monkeypatch.setattr("src.database.SessionLocal", sessionmaker(bind=new_engine))
    init_db()
    yield


def _make_wb(rows: list[list]) -> BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_import_riga_valida_completa():
    rows = [[
        "CTU 1234/2025 Tribunale di Roma — Bianchi c/ Verdi",
        date(2025, 3, 1), date(2025, 3, 10), date(2025, 3, 20),
        date(2025, 6, 18), date(2025, 7, 18), date(2025, 8, 17), date(2025, 9, 5),
        "in corso", None, "Nota operativa importante", None, None, None,
    ]]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    assert report["skipped"] == 0

    s = get_session()
    inc = s.query(Incarico).one()
    assert inc.tipo == "CTU"
    assert inc.numero_rg == "1234/2025"
    assert "Tribunale di Roma" in inc.tribunale
    assert inc.data_conferimento == date(2025, 3, 1)
    assert inc.data_giuramento == date(2025, 3, 10)
    assert inc.data_inizio_operazioni == date(2025, 3, 20)
    assert inc.stato == "attivo"
    assert inc.note == "Nota operativa importante"
    assert len(inc.eventi) == 4
    tipi_eventi = {e.tipo for e in inc.eventi}
    assert tipi_eventi == {"bozza", "osservazioni", "deposito", "udienza"}
    s.close()


def test_skip_righe_vuote():
    rows = [
        ["", None, None, None, None, None, None, None, None, None, None, None, None, None],
        [None] * 14,
        ["CTU 99/2025", date(2025, 1, 1), None, None, None, None, None, None,
         None, None, None, None, None, None],
    ]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    assert report["skipped"] == 2


def test_colonna_j_ignorata():
    """Anche se J ha valore, non deve essere usata."""
    rows = [[
        "CTU 1/2025", date(2025, 3, 1), None, None, None, None, None, None,
        "in corso", 42, None, None, None, None,
    ]]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    # J non viene salvata in nessun campo


def test_stato_chiuso_e_sospeso():
    rows = [
        ["CTU 1/2025", date(2025, 1, 1), None, None, None, None, None, None,
         "depositato", None, None, None, None, None],
        ["CTU 2/2025", date(2025, 1, 1), None, None, None, None, None, None,
         "Sospeso", None, None, None, None, None],
    ]
    importa_excel(_make_wb(rows))
    s = get_session()
    incs = {i.numero_rg: i for i in s.query(Incarico).all()}
    assert incs["1/2025"].stato == "chiuso"
    assert incs["2/2025"].stato == "sospeso"
    s.close()


def test_sospensione_importata():
    rows = [[
        "CTU 1/2025", date(2025, 1, 1), None, None, None, None, None, None,
        None, None, None, date(2025, 8, 1), date(2025, 8, 31), 31,
    ]]
    importa_excel(_make_wb(rows))
    s = get_session()
    inc = s.query(Incarico).one()
    assert len(inc.sospensioni) == 1
    sosp = inc.sospensioni[0]
    assert sosp.data_inizio == date(2025, 8, 1)
    assert sosp.data_fine == date(2025, 8, 31)
    assert "31" in sosp.motivo
    # Le sospensioni importate sono annotative: non devono incidere finche'
    # l'utente non lo conferma manualmente.
    assert sosp.incide_su_scadenze is False
    s.close()


def test_sospensione_importata_solo_data_inizio():
    rows = [[
        "CTU 2/2025", date(2025, 1, 1), None, None, None, None, None, None,
        None, None, None, date(2025, 8, 1), None, None,
    ]]
    importa_excel(_make_wb(rows))
    s = get_session()
    inc = s.query(Incarico).one()
    assert len(inc.sospensioni) == 1
    assert inc.sospensioni[0].incide_su_scadenze is False
    s.close()


def test_data_non_riconosciuta_finisce_in_report():
    rows = [[
        "CTU 1/2025", "non-una-data", None, None, None, None, None, None,
        None, None, None, None, None, None,
    ]]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    assert any("non-una-data" in err for err in report["date_errors"])


def test_descrizione_senza_rg_genera_anomalia():
    rows = [[
        "Incarico generico senza riferimenti",
        date(2025, 1, 1), None, None, None, None, None, None,
        None, None, None, None, None, None,
    ]]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    assert any("RG" in a for a in report["anomalies"])
    s = get_session()
    inc = s.query(Incarico).one()
    assert inc.numero_rg.startswith("IMPORT-")
    s.close()


def test_data_string_italiana():
    rows = [[
        "CTU 1/2025", "01/03/2025", None, None, None, None, None, None,
        None, None, None, None, None, None,
    ]]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    assert report["date_errors"] == []
    s = get_session()
    inc = s.query(Incarico).one()
    assert inc.data_conferimento == date(2025, 3, 1)
    s.close()


def test_origine_dato_import_excel():
    rows = [[
        "CTU 1/2025", date(2025, 1, 1), None, None, None, None, None, None,
        None, None, None, None, None, None,
    ]]
    importa_excel(_make_wb(rows))
    s = get_session()
    inc = s.query(Incarico).one()
    assert inc.origine_dato == "import_excel"
    s.close()


def test_duplicato_saltato():
    rows = [[
        "CTU 100/2025 Tribunale di Test",
        date(2025, 1, 1), None, date(2025, 1, 10), None, None, None, None,
        None, None, None, None, None, None,
    ]]
    r1 = importa_excel(_make_wb(rows))
    assert r1["imported"] == 1
    assert r1["duplicates"] == 0

    r2 = importa_excel(_make_wb(rows))
    assert r2["imported"] == 0
    assert r2["duplicates"] == 1
    assert any("duplicato" in a.lower() for a in r2["anomalies"])

    s = get_session()
    assert s.query(Incarico).count() == 1
    s.close()


def test_testo_in_cella_data_evento_salvato_come_nota_evento():
    rows = [[
        "CTU 200/2025", date(2025, 1, 1), None, None,
        "in attesa di conferma",  # E/bozza non parseable
        None, None, None,
        None, None, None, None, None, None,
    ]]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    assert any("non riconosciuto" in e.lower() or "in attesa" in e for e in report["date_errors"])

    s = get_session()
    inc = s.query(Incarico).one()
    eventi_bozza = [e for e in inc.eventi if e.tipo == "bozza"]
    assert len(eventi_bozza) == 1
    ev = eventi_bozza[0]
    assert ev.data is None
    assert "in attesa di conferma" in (ev.descrizione or "")
    s.close()


def test_testo_in_cella_data_b_genera_nota_evento():
    """Anche testo non parseable in colonne B/C/D viene preservato come evento nota."""
    rows = [[
        "CTU 300/2025", "data sconosciuta", None, None,
        None, None, None, None,
        None, None, None, None, None, None,
    ]]
    report = importa_excel(_make_wb(rows))
    assert report["imported"] == 1
    s = get_session()
    inc = s.query(Incarico).one()
    note_events = [e for e in inc.eventi if e.tipo == "nota"]
    assert len(note_events) >= 1
    assert any("data sconosciuta" in (e.descrizione or "") for e in note_events)
    s.close()


def test_incarico_import_evidenziato_come_da_correggere():
    """Quando il numero RG non e' rilevato, l'incarico ha numero IMPORT-N."""
    from src.utils import is_numero_da_correggere
    rows = [[
        "Incarico generico senza riferimenti",
        date(2025, 1, 1), None, None, None, None, None, None,
        None, None, None, None, None, None,
    ]]
    importa_excel(_make_wb(rows))
    s = get_session()
    inc = s.query(Incarico).one()
    assert is_numero_da_correggere(inc.numero_rg)
    s.close()


def test_parse_descrizione_formato_rg_con_punto():
    parsed = _parse_descrizione("CTU RG2531.2026 Parasole B. vs Ag Demanio")
    assert parsed["tipo"] == "CTU"
    assert parsed["numero_rg"] == "2531/2026"


def test_parse_descrizione_formato_procura_resa():
    parsed = _parse_descrizione("CTU Procura RESA 66 01 Barano")
    assert parsed["tipo"] == "Procura"
    assert parsed["numero_rg"] == "66/01"


def test_parse_descrizione_formato_rge():
    parsed = _parse_descrizione("CTU RGE 57.2024 ALTEA vs ESPOSITO")
    assert parsed["tipo"] == "CTU"
    assert parsed["numero_rg"] == "57/2024"


def test_parse_descrizione_formato_rge_con_underscore_dopo_anno():
    parsed = _parse_descrizione("CTU RGE 6629.2024_Tangenziale vs Gatto_Ordine a fare")
    assert parsed["tipo"] == "Ordine a fare"
    assert parsed["numero_rg"] == "6629/2024"


def test_parse_descrizione_formato_nr_con_underscore_e_no_data_nascita():
    parsed = _parse_descrizione(
        "CTU Procura- RE.S.A. nr. 68_01\nDi Meglio Lorenzo (Ischia (NA) il 03/06/19320)"
    )
    assert parsed["tipo"] == "Procura"
    assert parsed["numero_rg"] == "68/01"
