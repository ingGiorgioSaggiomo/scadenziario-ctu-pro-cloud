"""Scadenziario CTU Pro - Interfaccia Streamlit."""

import os
from datetime import date
from html import escape
from threading import Thread

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from src.database import elimina_dati_demo, elimina_incarico, get_session, init_db
from src.backup_tools import crea_backup_database, crea_backup_giornaliero
from src.deadline_engine import genera_eventi_standard
from src.export_tools import genera_excel_export
from src.import_excel import importa_excel
from src.models import Documento, Evento, Incarico, Pagamento, Sospensione, Termine
from src.monitoraggio import etichetta_fonte_database, genera_voci_monitoraggio
from src.pagamenti import (
    TIPI_PAGAMENTO,
    calcola_totale_fattura,
    fmt_euro,
    importo_dovuto_pagamento,
    riepilogo_pagamenti,
)
from src.termine_eventi import (
    aggiorna_termine,
    completa_bozza,
    completa_osservazioni,
    ricalcola_termini_incarico,
    registra_storico_termine,
    rileva_incongruenze_incarico,
    scollega_evento_prima_eliminazione,
    sincronizza_evento_da_termine,
)
from src.utils import (
    ALERT_COLORS,
    ALERT_LABEL,
    ALERT_PRIORITY,
    DECORRENZE,
    PRIORITA,
    STATI_EVENTO,
    STATI_INCARICO,
    TIPI_EVENTO,
    TIPI_INCARICO,
    TIPI_TERMINE,
    alert_badge_html,
    attesa_osservazioni_da_mostrare_dashboard,
    applica_stato_evento,
    calcola_scadenza_termine,
    classifica_per_dashboard,
    fmt_date,
    is_numero_da_correggere,
    metric_key_dashboard,
    stato_evento,
    tipi_evento_gestiti_da_termini,
    trova_prossima_attivita_dashboard,
)

OFFLINE_MODE = os.environ.get("SCADENZIARIO_OFFLINE_MODE") == "1"
st.set_page_config(page_title="Scadenziario CTU Pro", layout="wide", page_icon=None)


@st.cache_resource(show_spinner=False)
def _initialize_database():
    init_db()


def _run_daily_backup():
    try:
        crea_backup_giornaliero()
    except Exception as exc:
        print(f"Backup giornaliero non riuscito: {type(exc).__name__}: {exc}")


@st.cache_resource(show_spinner=False)
def _start_daily_backup():
    thread = Thread(target=_run_daily_backup, name="scadenziario-backup", daemon=True)
    thread.start()
    return thread


def check_password() -> bool:
    """Restituisce True se l'utente ha inserito la password corretta."""
    if os.environ.get("SCADENZIARIO_LOCAL_MODE") == "1":
        return True

    # Se non c'e' nessuna password configurata, disattiva il login solo per lo sviluppo locale.
    try:
        target_password = (
            st.secrets.get("ACCESS_PASSWORD")
            or st.secrets.get("password")
            or os.environ.get("ACCESS_PASSWORD")
        )
        online_database = bool(st.secrets.get("DATABASE_URL") or os.environ.get("DATABASE_URL"))
    except Exception:
        target_password = os.environ.get("ACCESS_PASSWORD")
        online_database = bool(os.environ.get("DATABASE_URL"))

    if not target_password:
        if online_database or os.environ.get("RENDER") or os.environ.get("PORT"):
            st.error("Password di accesso non configurata. Imposta ACCESS_PASSWORD nei segreti del servizio cloud.")
            return False
        return True

    def password_entered():
        """Verifica se la password inserita e' corretta."""
        if st.session_state["password"] == target_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # non memorizza la password
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    # Mostra l'interfaccia di login
    st.title("Accesso Scadenziario CTU Pro")
    st.text_input(
        "Inserisci la password di accesso:", type="password", on_change=password_entered, key="password"
    )
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Password errata")
    return False


if not OFFLINE_MODE:
    try:
        _initialize_database()
    except SQLAlchemyError as exc:
        db_error = getattr(exc, "orig", exc)
        print(f"Database connection failed: {type(db_error).__name__}: {db_error}")
        st.error("Database online non raggiungibile.")
        st.info(
            "Se sei sul PC puoi aprire il collegamento offline per consultare l'ultimo backup. "
            "Se sei online, verifica la disponibilita di Supabase e la configurazione DATABASE_URL."
        )
        st.stop()

# Controllo della password per accessi online
if not check_password():
    st.stop()

if os.environ.get("SCADENZIARIO_LOCAL_MODE") == "1" and not OFFLINE_MODE:
    _start_daily_backup()

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    h1 {font-size: 1.7rem !important; margin-bottom: 0.5rem;}
    h2 {font-size: 1.3rem !important; margin-top: 1rem;}
    div[data-testid="stMetric"] {background:#f5f5f5; padding:0.5rem 0.8rem; border-radius:6px;}
    .dashboard-table-wrap {width:100%; overflow-x:auto;}
    .dashboard-table {width:100%; border-collapse:collapse; table-layout:fixed;}
    .dashboard-table th {padding:8px; background:#eceff1; text-align:left; overflow-wrap:anywhere;}
    .dashboard-table td {
        padding:8px;
        border-bottom:1px solid #e0e0e0;
        vertical-align:top;
        overflow-wrap:anywhere;
    }
    .dashboard-table .cell-muted {color:#555;}
    .dashboard-table .cell-number {text-align:right;}
    .mobile-open-link {display:none;}
    @media (max-width: 760px) {
        .block-container {padding:0.75rem;}
        h1 {font-size:1.35rem !important;}
        h2 {font-size:1.15rem !important;}
        h3 {font-size:1rem !important;}
        div[data-testid="stMetric"] {padding:0.45rem 0.55rem; min-height:68px;}
        div[data-testid="stMetricLabel"] p {font-size:0.72rem;}
        div[data-testid="stMetricValue"] {font-size:1.25rem;}
        .dashboard-table-wrap {overflow-x:visible;}
        .dashboard-table,
        .dashboard-table tbody,
        .dashboard-table tr,
        .dashboard-table td {display:block; width:100%;}
        .dashboard-table {
            table-layout:auto;
            border-collapse:separate;
            border-spacing:0 0.75rem;
        }
        .dashboard-table colgroup,
        .dashboard-table thead {display:none;}
        .dashboard-table tr {
            border:1px solid #d8dde3;
            border-radius:8px;
            background:#fff;
            box-shadow:0 1px 2px rgba(0,0,0,0.04);
            overflow:hidden;
        }
        .dashboard-table td {
            display:grid;
            grid-template-columns:7.5rem minmax(0, 1fr);
            gap:0.6rem;
            align-items:start;
            border-bottom:1px solid #eef1f4;
            padding:0.6rem 0.7rem;
            font-size:0.92rem;
        }
        .dashboard-table td:last-child {border-bottom:0;}
        .dashboard-table td::before {
            content:attr(data-label);
            color:#68717d;
            font-weight:600;
            font-size:0.78rem;
        }
        .dashboard-table .cell-number {text-align:left;}
        .dashboard-table a {font-size:1rem; line-height:1.35;}
        .mobile-open-link {
            display:inline-block;
            margin-top:0.55rem;
            padding:0.42rem 0.7rem;
            border-radius:6px;
            background:#1565c0;
            color:#fff !important;
            text-decoration:none !important;
            font-weight:700;
            font-size:0.88rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if OFFLINE_MODE:
    st.warning(
        "MODALITA OFFLINE - SOLA LETTURA. Stai consultando l'ultimo backup locale; "
        "le modifiche sono disabilitate."
    )


# ------------------------- helpers -------------------------

def _select_incarico(session, label="Incarico", key=None):
    incarichi = session.query(Incarico).order_by(Incarico.data_conferimento.desc()).all()
    if not incarichi:
        st.info("Nessun incarico presente. Crea un incarico dalla pagina 'Nuovo incarico'.")
        return None
    options = {f"{i.tipo} {i.numero_rg} - {i.tribunale}": i for i in incarichi}
    scelta = st.selectbox(label, list(options.keys()), key=key)
    return options[scelta]


def _safe_backup(motivo: str) -> None:
    backup = crea_backup_database(motivo)
    if backup is not None:
        st.caption(f"Backup creato: {backup.name}")


def _render_incarico_editor(session, inc, prefix: str):
    with st.form(f"{prefix}_inc_form_{inc.id}"):
        c1, c2 = st.columns(2)
        with c1:
            new_numero = st.text_input("Numero procedura", value=inc.numero_rg or "")
            new_tipo = st.selectbox(
                "Tipo incarico", TIPI_INCARICO,
                index=TIPI_INCARICO.index(inc.tipo) if inc.tipo in TIPI_INCARICO else 0,
                key=f"{prefix}_tipo_{inc.id}",
            )
            new_tribunale = st.text_input("Ufficio", value=inc.tribunale or "")
            new_priorita = st.selectbox(
                "Priorita", PRIORITA,
                index=PRIORITA.index(inc.priorita) if inc.priorita in PRIORITA else 1,
                key=f"{prefix}_prio_{inc.id}",
            )
        with c2:
            new_stato = st.selectbox(
                "Stato", STATI_INCARICO,
                index=STATI_INCARICO.index(inc.stato) if inc.stato in STATI_INCARICO else 0,
                key=f"{prefix}_stato_{inc.id}",
            )
            new_oggetto = st.text_area(
                "Oggetto / descrizione",
                value=inc.oggetto or "",
                height=80,
                key=f"{prefix}_oggetto_{inc.id}",
            )
            new_note = st.text_area(
                "Note",
                value=inc.note or "",
                height=80,
                key=f"{prefix}_note_{inc.id}",
            )
        if st.form_submit_button("Salva incarico", type="primary"):
            inc.numero_rg = new_numero.strip()
            inc.tipo = new_tipo
            inc.tribunale = new_tribunale.strip()
            inc.priorita = new_priorita
            inc.stato = new_stato
            inc.oggetto = new_oggetto or None
            inc.note = new_note or None
            session.commit()
            st.success("Incarico aggiornato.")
            st.rerun()

    bozza_inviata = bool(getattr(inc, "data_invio_bozza", None)) or any(
        getattr(evento, "tipo", None) == "bozza" and getattr(evento, "data", None)
        for evento in getattr(inc, "eventi", [])
    )
    if bozza_inviata and inc.stato == "attivo":
        st.info("Bozza inviata: se stai attendendo le osservazioni delle parti puoi sospendere il richiamo operativo.")
        if st.button("Imposta attesa osservazioni", key=f"{prefix}_attesa_osservazioni_{inc.id}"):
            if not inc.data_invio_bozza:
                date_bozza = [
                    evento.data
                    for evento in getattr(inc, "eventi", [])
                    if getattr(evento, "tipo", None) == "bozza" and getattr(evento, "data", None)
                ]
                if date_bozza:
                    inc.data_invio_bozza = min(date_bozza)
            inc.stato = "attesa osservazioni"
            session.commit()
            st.success("Stato aggiornato in attesa osservazioni.")
            st.rerun()
    elif inc.stato == "attesa osservazioni":
        st.info("Questo incarico e' in attesa delle osservazioni alla bozza; non viene mostrato tra i lavori immediati della dashboard.")


def _termini_in_ordine_cronologico(inc):
    return sorted(
        list(inc.termini or []),
        key=lambda t: (calcola_scadenza_termine(inc, t) or date.max, t.id or 0),
    )


def _render_workflow_termini(session, inc, prefix: str):
    bozza = next((
        t for t in _termini_in_ordine_cronologico(inc)
        if t.tipo_termine == "bozza" and t.attivo and not t.completato
    ), None)
    osservazioni = next((
        t for t in _termini_in_ordine_cronologico(inc)
        if t.tipo_termine == "osservazioni" and t.attivo and not t.completato
    ), None)

    if bozza is not None and inc.stato == "attivo":
        with st.expander("Avanzamento guidato: invio bozza"):
            st.caption(
                "Confermando l'invio, il termine bozza viene completato, la data viene registrata "
                "e l'incarico passa automaticamente in attesa osservazioni."
            )
            with st.form(f"{prefix}_workflow_bozza_{bozza.id}"):
                data_invio = st.date_input("Data effettiva invio bozza", value=date.today())
                if st.form_submit_button("Conferma invio bozza", type="primary"):
                    completa_bozza(session, inc, bozza, data_invio)
                    session.commit()
                    st.success("Bozza completata; incarico impostato in attesa osservazioni.")
                    st.rerun()

    if osservazioni is not None and inc.stato == "attesa osservazioni":
        with st.expander("Avanzamento guidato: fine attesa osservazioni"):
            st.caption(
                "Usa questa conferma alla scadenza del termine o quando le osservazioni sono pervenute. "
                "L'incarico torna operativo e la dashboard passa al deposito."
            )
            data_default = calcola_scadenza_termine(inc, osservazioni) or date.today()
            with st.form(f"{prefix}_workflow_osservazioni_{osservazioni.id}"):
                data_fine = st.date_input("Data fine attesa osservazioni", value=data_default)
                if st.form_submit_button("Conferma fine attesa", type="primary"):
                    completa_osservazioni(session, inc, osservazioni, data_fine)
                    session.commit()
                    st.success("Attesa conclusa; incarico nuovamente operativo.")
                    st.rerun()


def _render_termini_editor(session, inc, prefix: str):
    _render_workflow_termini(session, inc, prefix)

    if inc.termini:
        rows = []
        termini_ordinati = _termini_in_ordine_cronologico(inc)
        for t in termini_ordinati:
            scad = calcola_scadenza_termine(inc, t)
            rows.append({
                "ID": t.id,
                "Tipo": t.tipo_termine,
                "Giorni": t.giorni,
                "Decorrenza": t.decorrenza,
                "Manual": fmt_date(t.data_manual),
                "Scadenza calcolata": fmt_date(scad),
                "Attivo": "si" if t.attivo else "no",
                "Completato": "si" if t.completato else "no",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        with st.expander("Modifica / elimina termine"):
            ids = [t.id for t in termini_ordinati]
            sel = st.selectbox("Seleziona ID", ids, key=f"{prefix}_termine_action_{inc.id}")
            term = session.get(Termine, int(sel))
            if term is None:
                st.error("Termine non trovato.")
                st.stop()
            with st.form(f"{prefix}_term_edit_{inc.id}_{term.id}"):
                c1, c2 = st.columns(2)
                with c1:
                    tipo_mod = st.selectbox(
                        "Tipo termine",
                        TIPI_TERMINE,
                        index=TIPI_TERMINE.index(term.tipo_termine) if term.tipo_termine in TIPI_TERMINE else 0,
                    )
                    giorni_mod = st.number_input(
                        "Giorni",
                        min_value=0,
                        value=int(term.giorni or 0),
                        step=1,
                    )
                    attivo_mod = st.checkbox("Attivo", value=bool(term.attivo))
                    prorogato_mod = st.checkbox("Prorogato", value=bool(term.prorogato))
                with c2:
                    decorrenza_mod = st.selectbox(
                        "Decorrenza",
                        DECORRENZE,
                        index=DECORRENZE.index(term.decorrenza) if term.decorrenza in DECORRENZE else 0,
                    )
                    data_manual_mod = st.date_input("Data manuale", value=term.data_manual)
                    workflow_richiesto = term.tipo_termine in {"bozza", "osservazioni"} and not term.completato
                    completato_mod = st.checkbox(
                        "Completato",
                        value=bool(term.completato),
                        disabled=workflow_richiesto,
                        help="Per bozza e osservazioni usa l'avanzamento guidato con conferma della data.",
                    )
                note_mod = st.text_area("Note termine", value=term.note or "", height=70)
                motivo_mod = st.text_input("Motivo della modifica", placeholder="Esempio: proroga concessa dal Tribunale")
                c3, c4 = st.columns(2)
                salva = c3.form_submit_button("Salva modifiche", type="primary")
                elimina = c4.form_submit_button("Elimina termine", type="secondary")
                if salva:
                    if decorrenza_mod == "data_manual" and data_manual_mod is None:
                        st.error("Inserisci la data manuale.")
                        st.stop()
                    aggiorna_termine(
                        session,
                        inc,
                        term,
                        tipo_termine=tipo_mod,
                        giorni=int(giorni_mod),
                        decorrenza=decorrenza_mod,
                        data_manual=data_manual_mod,
                        attivo=attivo_mod,
                        completato=completato_mod,
                        prorogato=prorogato_mod,
                        note=note_mod,
                        motivo=motivo_mod,
                    )
                    session.commit()
                    st.success("Termine, Evento collegato e cronologia aggiornati.")
                    st.rerun()
                if elimina:
                    _safe_backup("prima_elimina_termine")
                    registra_storico_termine(session, term, "eliminato", motivo_mod or "Eliminazione manuale")
                    scollega_evento_prima_eliminazione(session, term)
                    session.flush()
                    session.delete(term)
                    session.commit()
                    st.rerun()

        if inc.storico_termini:
            with st.expander("Cronologia modifiche termini"):
                storico_rows = []
                for voce in sorted(inc.storico_termini, key=lambda s: (s.modificato_il, s.id), reverse=True):
                    storico_rows.append({
                        "Data e ora": voce.modificato_il.strftime("%d/%m/%Y %H:%M"),
                        "Azione": voce.azione,
                        "Tipo": voce.tipo_termine,
                        "Scadenza": fmt_date(voce.data_scadenza),
                        "Attivo": "si" if voce.attivo else "no",
                        "Completato": "si" if voce.completato else "no",
                        "Motivo": voce.motivo or "",
                    })
                st.dataframe(pd.DataFrame(storico_rows), hide_index=True, use_container_width=True)
    else:
        st.info("Nessun termine definito.")

    st.markdown("---")
    st.subheader("Aggiungi termine")
    with st.form(f"{prefix}_nuovo_termine_{inc.id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            tipo_t = st.selectbox("Tipo termine", TIPI_TERMINE, key=f"{prefix}_tipo_t_{inc.id}")
            giorni = st.number_input(
                "Giorni",
                min_value=0,
                value=30,
                step=1,
                key=f"{prefix}_giorni_{inc.id}",
            )
        with c2:
            decorrenza = st.selectbox("Decorrenza", DECORRENZE, key=f"{prefix}_decorr_{inc.id}")
            data_manual = st.date_input(
                "Data manuale (solo se decorrenza = data_manual)",
                value=None,
                key=f"{prefix}_data_manual_{inc.id}",
            )
        attivo = st.checkbox("Attivo", value=True, key=f"{prefix}_attivo_{inc.id}")
        if st.form_submit_button("Aggiungi termine", type="primary"):
            giorni_effettivi = 0 if decorrenza == "data_manual" else int(giorni)
            t = Termine(
                incarico_id=inc.id,
                tipo_termine=tipo_t,
                giorni=giorni_effettivi,
                decorrenza=decorrenza,
                data_manual=data_manual if decorrenza == "data_manual" else None,
                tipo_computo="naturali",
                attivo=attivo,
            )
            t.data_scadenza = calcola_scadenza_termine(inc, t)
            session.add(t)
            session.flush()
            sincronizza_evento_da_termine(session, inc, t)
            registra_storico_termine(session, t, "creato", "Creazione manuale")
            session.commit()
            st.success("Termine aggiunto e collegato al relativo Evento.")
            st.rerun()

    st.markdown("---")
    st.subheader("Date di riferimento dell'incarico")
    with st.form(f"{prefix}_date_riferimento_{inc.id}"):
        c1, c2, c3 = st.columns(3)
        d_iniz = c1.date_input(
            "Inizio operazioni",
            value=inc.data_inizio_operazioni,
            key=f"{prefix}_d_iniz_{inc.id}",
        )
        d_bozza = c2.date_input(
            "Invio bozza",
            value=inc.data_invio_bozza,
            key=f"{prefix}_d_bozza_{inc.id}",
        )
        d_oss = c3.date_input(
            "Ricezione osservazioni",
            value=inc.data_ricezione_osservazioni,
            key=f"{prefix}_d_oss_{inc.id}",
        )
        if st.form_submit_button("Salva date"):
            inc.data_inizio_operazioni = d_iniz or None
            inc.data_invio_bozza = d_bozza or None
            inc.data_ricezione_osservazioni = d_oss or None
            ricalcola_termini_incarico(session, inc, "Modifica date di riferimento")
            session.commit()
            st.success("Date, scadenze collegate e cronologia aggiornate.")
            st.rerun()


def _render_eventi_editor(session, inc, prefix: str):
    tab_scadenze, tab_eventi = st.tabs(["Scadenze calcolate", "Eventi"])

    with tab_scadenze:
        eventi_calc = genera_eventi_standard(inc, inc.termini)
        if not eventi_calc:
            st.info("Nessun termine attivo per cui calcolare scadenze.")
        else:
            for sc in sorted(eventi_calc, key=lambda e: e.data_scadenza):
                termine = next(
                    (
                        t for t in inc.termini
                        if t.id == sc.termine_id
                    ),
                    None,
                )
                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                col1.markdown(
                    f"**{sc.tipo_termine}** - {fmt_date(sc.data_scadenza)} "
                    f"({sc.giorni_residui:+d} gg)"
                )
                col2.markdown(alert_badge_html(sc.alert), unsafe_allow_html=True)
                col3.write("Completato" if sc.completato else "In corso")
                if not sc.completato and termine:
                    if termine.tipo_termine in {"bozza", "osservazioni"}:
                        col4.caption("Usa l'avanzamento guidato nella scheda Termini")
                    elif col4.button(
                        "Marca completato",
                        key=f"{prefix}_calc_compl_{termine.id}",
                    ):
                        registra_storico_termine(session, termine, "prima_completamento")
                        termine.completato = True
                        sincronizza_evento_da_termine(session, inc, termine)
                        registra_storico_termine(session, termine, "completato")
                        session.commit()
                        st.rerun()

    with tab_eventi:
        eventi_visibili = [e for e in inc.eventi if not getattr(e, "annullato", False)]
        if eventi_visibili:
            tipi_gestiti = tipi_evento_gestiti_da_termini(inc)
            eventi_sostituiti = [
                e for e in eventi_visibili
                if str(e.tipo or "").strip().lower() in tipi_gestiti
            ]
            if eventi_sostituiti:
                tipi_label = ", ".join(sorted({e.tipo for e in eventi_sostituiti}))
                st.info(
                    "Per i tipi " + tipi_label
                    + " la dashboard usa il Termine attivo. Gli Eventi omonimi "
                    "restano visibili come storico e non devono essere aggiornati separatamente."
                )
            rows = []
            for e in eventi_visibili:
                gestito_da_termine = str(e.tipo or "").strip().lower() in tipi_gestiti
                rows.append({
                    "ID": e.id,
                    "Tipo": e.tipo,
                    "Data": fmt_date(e.data),
                    "Ora": e.ora or "-",
                    "Luogo": e.luogo or "-",
                    "Descrizione": (e.descrizione or "")[:100],
                    "Stato": stato_evento(e),
                    "Fonte dashboard": "Termine" if gestito_da_termine else "Evento",
                    "Termine ID": e.termine_id or "-",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            with st.expander("Modifica / annulla evento"):
                ids = [e.id for e in eventi_visibili]
                sel = st.selectbox("Seleziona ID", ids, key=f"{prefix}_ev_action_{inc.id}")
                ev = session.get(Evento, sel)
                if ev.termine_id is not None:
                    st.info(
                        f"Questo Evento e' sincronizzato con il Termine {ev.termine_id}. "
                        "Modificalo dalla scheda Termini."
                    )
                else:
                    with st.form(f"{prefix}_ev_form_{ev.id}"):
                        c1, c2, c3 = st.columns([2, 2, 3])
                        with c1:
                            new_tipo_e = st.selectbox(
                                "Tipo evento",
                                TIPI_EVENTO,
                                index=TIPI_EVENTO.index(ev.tipo) if ev.tipo in TIPI_EVENTO else 0,
                                key=f"{prefix}_tipoev_{ev.id}",
                            )
                            new_data = st.date_input(
                                "Data prevista",
                                value=ev.data,
                                key=f"{prefix}_dataev_{ev.id}",
                            )
                            new_ora = st.text_input(
                                "Ora",
                                value=ev.ora or "",
                                key=f"{prefix}_oraev_{ev.id}",
                            )
                        with c2:
                            new_stato_e = st.selectbox(
                                "Stato evento",
                                STATI_EVENTO,
                                index=STATI_EVENTO.index(stato_evento(ev)),
                                key=f"{prefix}_statoev_{ev.id}",
                            )
                            new_luogo = st.text_input(
                                "Luogo",
                                value=ev.luogo or "",
                                key=f"{prefix}_luogoev_{ev.id}",
                            )
                        with c3:
                            new_descr = st.text_area(
                                "Note evento",
                                value=ev.descrizione or "",
                                height=90,
                                key=f"{prefix}_descrev_{ev.id}",
                            )
                        c4, c5 = st.columns(2)
                        save = c4.form_submit_button("Salva evento")
                        delete = c5.form_submit_button("Annulla evento", type="secondary")
                        if save:
                            ev.tipo = new_tipo_e
                            ev.data = new_data or None
                            ev.ora = new_ora or None
                            ev.luogo = new_luogo or None
                            applica_stato_evento(ev, new_stato_e)
                            ev.descrizione = new_descr or None
                            session.commit()
                            st.success("Evento aggiornato.")
                            st.rerun()
                        if delete:
                            _safe_backup("prima_annulla_evento")
                            ev.annullato = True
                            session.commit()
                            st.rerun()
        else:
            st.info("Nessun evento registrato.")

        st.markdown("---")
        st.subheader("Nuovo evento")
        with st.form(f"{prefix}_nuovo_evento_{inc.id}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                tipo_e = st.selectbox("Tipo", TIPI_EVENTO, key=f"{prefix}_new_ev_tipo_{inc.id}")
                data_e = st.date_input("Data", value=date.today(), key=f"{prefix}_new_ev_data_{inc.id}")
                ora_e = st.text_input("Ora (HH:MM)", key=f"{prefix}_new_ev_ora_{inc.id}")
            with c2:
                luogo_e = st.text_input("Luogo", key=f"{prefix}_new_ev_luogo_{inc.id}")
                descr_e = st.text_area("Descrizione", height=80, key=f"{prefix}_new_ev_descr_{inc.id}")
            if st.form_submit_button("Aggiungi evento", type="primary"):
                ev = Evento(
                    incarico_id=inc.id,
                    tipo=tipo_e,
                    data=data_e,
                    ora=ora_e or None,
                    luogo=luogo_e or None,
                    descrizione=descr_e or None,
                )
                session.add(ev)
                session.commit()
                st.success("Evento aggiunto.")
                st.rerun()


def _render_sospensioni_editor(session, inc, prefix: str):
    if inc.sospensioni:
        rows = []
        for s in inc.sospensioni:
            rows.append({
                "ID": s.id,
                "Inizio": fmt_date(s.data_inizio),
                "Fine": fmt_date(s.data_fine),
                "Incide": "si" if s.incide_su_scadenze else "no",
                "Motivo": (s.motivo or "")[:100],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        with st.expander("Elimina sospensione"):
            ids = [s.id for s in inc.sospensioni]
            sel = st.selectbox("ID", ids, key=f"{prefix}_sosp_del_{inc.id}")
            if st.button("Elimina", type="secondary", key=f"{prefix}_sosp_del_btn_{inc.id}_{sel}"):
                _safe_backup("prima_elimina_sospensione")
                s = session.get(Sospensione, sel)
                session.delete(s)
                session.flush()
                session.expire(inc, ["sospensioni"])
                ricalcola_termini_incarico(session, inc, "Eliminazione sospensione")
                session.commit()
                st.rerun()
    else:
        st.info("Nessuna sospensione registrata.")

    st.markdown("---")
    st.subheader("Nuova sospensione")
    with st.form(f"{prefix}_nuova_sosp_{inc.id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            di = st.date_input("Data sospensione", value=date.today(), key=f"{prefix}_sosp_di_{inc.id}")
            df = st.date_input("Data ripresa", value=None, key=f"{prefix}_sosp_df_{inc.id}")
        with c2:
            incide = st.checkbox("Incide sulle scadenze", value=True, key=f"{prefix}_sosp_incide_{inc.id}")
            motivo = st.text_area("Note / motivo", height=80, key=f"{prefix}_sosp_motivo_{inc.id}")
        if st.form_submit_button("Aggiungi sospensione", type="primary"):
            if df and df < di:
                st.error("La data di ripresa non può precedere la data di sospensione.")
                return
            s = Sospensione(
                incarico_id=inc.id,
                data_inizio=di,
                data_fine=df or None,
                motivo=motivo or None,
                incide_su_scadenze=incide,
            )
            session.add(s)
            session.flush()
            session.expire(inc, ["sospensioni"])
            ricalcola_termini_incarico(session, inc, "Nuova sospensione")
            session.commit()
            st.success("Sospensione aggiunta.")
            st.rerun()


def _render_documenti_editor(session, inc, prefix: str):
    if inc.documenti:
        rows = []
        for doc in inc.documenti:
            rows.append({
                "ID": doc.id,
                "Nome": doc.nome,
                "Tipo": doc.tipo or "-",
                "Data": fmt_date(doc.data_documento),
                "Percorso": doc.percorso or "-",
                "Note": (doc.note or "")[:100],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        with st.expander("Modifica / elimina documento"):
            ids = [doc.id for doc in inc.documenti]
            sel = st.selectbox("Seleziona ID", ids, key=f"{prefix}_doc_action_{inc.id}")
            doc = session.get(Documento, sel)
            with st.form(f"{prefix}_doc_form_{doc.id}"):
                c1, c2 = st.columns(2)
                with c1:
                    nome = st.text_input("Nome", value=doc.nome or "", key=f"{prefix}_doc_nome_{doc.id}")
                    tipo = st.text_input("Tipo", value=doc.tipo or "", key=f"{prefix}_doc_tipo_{doc.id}")
                    data_doc = st.date_input(
                        "Data documento",
                        value=doc.data_documento,
                        key=f"{prefix}_doc_data_{doc.id}",
                    )
                with c2:
                    percorso = st.text_input("Percorso", value=doc.percorso or "", key=f"{prefix}_doc_perc_{doc.id}")
                    note = st.text_area("Note", value=doc.note or "", height=80, key=f"{prefix}_doc_note_{doc.id}")
                c3, c4 = st.columns(2)
                save = c3.form_submit_button("Salva documento")
                delete = c4.form_submit_button("Elimina documento", type="secondary")
                if save:
                    if not nome.strip():
                        st.error("Il nome documento e' obbligatorio.")
                    else:
                        doc.nome = nome.strip()
                        doc.tipo = tipo or None
                        doc.data_documento = data_doc or None
                        doc.percorso = percorso or None
                        doc.note = note or None
                        session.commit()
                        st.success("Documento aggiornato.")
                        st.rerun()
                if delete:
                    _safe_backup("prima_elimina_documento")
                    session.delete(doc)
                    session.commit()
                    st.rerun()
    else:
        st.info("Nessun documento registrato.")

    st.markdown("---")
    st.subheader("Nuovo documento")
    with st.form(f"{prefix}_nuovo_doc_{inc.id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nome = st.text_input("Nome documento *", key=f"{prefix}_new_doc_nome_{inc.id}")
            tipo = st.text_input("Tipo", key=f"{prefix}_new_doc_tipo_{inc.id}")
            data_doc = st.date_input("Data documento", value=None, key=f"{prefix}_new_doc_data_{inc.id}")
        with c2:
            percorso = st.text_input("Percorso file", key=f"{prefix}_new_doc_perc_{inc.id}")
            note = st.text_area("Note", height=80, key=f"{prefix}_new_doc_note_{inc.id}")
        if st.form_submit_button("Aggiungi documento", type="primary"):
            if not nome.strip():
                st.error("Il nome documento e' obbligatorio.")
            else:
                doc = Documento(
                    incarico_id=inc.id,
                    nome=nome.strip(),
                    tipo=tipo or None,
                    data_documento=data_doc or None,
                    percorso=percorso or None,
                    note=note or None,
                )
                session.add(doc)
                session.commit()
                st.success("Documento aggiunto.")
                st.rerun()


def _render_pagamenti_editor(session, inc, prefix: str):
    riepilogo = riepilogo_pagamenti(inc.pagamenti)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dovuto/liquidato", fmt_euro(riepilogo["totale_dovuto"]))
    c2.metric("Acconti ricevuti", fmt_euro(riepilogo["acconti_ricevuti"]))
    c3.metric("Totale ricevuto", fmt_euro(riepilogo["totale_ricevuto"]))
    c4.metric("Sospeso/residuo", fmt_euro(riepilogo["residuo"]))

    if inc.pagamenti:
        rows = []
        for pagamento in inc.pagamenti:
            rows.append({
                "ID": pagamento.id,
                "Tipo": pagamento.tipo,
                "Descrizione": pagamento.descrizione or "",
                "Imponibile": fmt_euro(pagamento.imponibile),
                "Spese": fmt_euro(pagamento.spese),
                "Dovuto da incassare": fmt_euro(importo_dovuto_pagamento(pagamento)),
                "Ricevuto": fmt_euro(pagamento.importo_ricevuto),
                "Data rif.": fmt_date(pagamento.data_riferimento),
                "Data pagamento": fmt_date(pagamento.data_pagamento),
                "Pagatore": pagamento.pagatore or "",
                "Note": (pagamento.note or "")[:100],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        with st.expander("Modifica / elimina pagamento"):
            ids = [pagamento.id for pagamento in inc.pagamenti]
            sel = st.selectbox("Seleziona ID", ids, key=f"{prefix}_pag_action_{inc.id}")
            pagamento = session.get(Pagamento, sel)
            with st.form(f"{prefix}_pag_form_{pagamento.id}"):
                c1, c2 = st.columns(2)
                with c1:
                    tipo = st.selectbox(
                        "Tipo",
                        TIPI_PAGAMENTO,
                        index=TIPI_PAGAMENTO.index(pagamento.tipo) if pagamento.tipo in TIPI_PAGAMENTO else 0,
                        key=f"{prefix}_pag_tipo_{pagamento.id}",
                    )
                    descrizione = st.text_input(
                        "Descrizione",
                        value=pagamento.descrizione or "",
                        key=f"{prefix}_pag_desc_{pagamento.id}",
                    )
                    imponibile = st.number_input(
                        "Imponibile",
                        min_value=0.0,
                        value=float(pagamento.imponibile or 0),
                        step=100.0,
                        format="%.2f",
                        key=f"{prefix}_pag_imponibile_{pagamento.id}",
                    )
                    spese = st.number_input(
                        "Spese liquidate",
                        min_value=0.0,
                        value=float(pagamento.spese or 0),
                        step=50.0,
                        format="%.2f",
                        key=f"{prefix}_pag_spese_{pagamento.id}",
                    )
                    calcolo = calcola_totale_fattura(imponibile, spese)
                    importo_dovuto_manual = st.number_input(
                        "Dovuto manuale se non usi imponibile/spese",
                        help="Usato solo se imponibile e spese sono entrambi a 0.",
                        min_value=0.0,
                        value=float(pagamento.importo_dovuto or 0),
                        step=100.0,
                        format="%.2f",
                        key=f"{prefix}_pag_dovuto_manual_{pagamento.id}",
                    )
                    st.caption(
                        "Cassa 4%: "
                        f"{fmt_euro(calcolo['cassa'])} | Bollo: {fmt_euro(calcolo['bollo'])} | "
                        f"Totale calcolato: {fmt_euro(calcolo['totale'])}"
                    )
                    data_riferimento = st.date_input(
                        "Data decreto / mandato",
                        value=pagamento.data_riferimento,
                        key=f"{prefix}_pag_data_rif_{pagamento.id}",
                    )
                with c2:
                    importo_ricevuto = st.number_input(
                        "Importo ricevuto",
                        min_value=0.0,
                        value=float(pagamento.importo_ricevuto or 0),
                        step=100.0,
                        format="%.2f",
                        key=f"{prefix}_pag_ricevuto_{pagamento.id}",
                    )
                    data_pagamento = st.date_input(
                        "Data pagamento",
                        value=pagamento.data_pagamento,
                        key=f"{prefix}_pag_data_pag_{pagamento.id}",
                    )
                    pagatore = st.text_input(
                        "Pagatore",
                        value=pagamento.pagatore or "",
                        key=f"{prefix}_pag_pagatore_{pagamento.id}",
                    )
                    note = st.text_area(
                        "Note",
                        value=pagamento.note or "",
                        height=80,
                        key=f"{prefix}_pag_note_{pagamento.id}",
                    )
                c3, c4 = st.columns(2)
                save = c3.form_submit_button("Salva pagamento")
                delete = c4.form_submit_button("Elimina pagamento", type="secondary")
                if save:
                    pagamento.tipo = tipo
                    pagamento.descrizione = descrizione or None
                    pagamento.imponibile = imponibile
                    pagamento.spese = spese
                    pagamento.importo_dovuto = calcolo["totale"] if imponibile or spese else importo_dovuto_manual
                    pagamento.importo_ricevuto = importo_ricevuto
                    pagamento.data_riferimento = data_riferimento or None
                    pagamento.data_pagamento = data_pagamento or None
                    pagamento.pagatore = pagatore or None
                    pagamento.note = note or None
                    session.commit()
                    st.success("Pagamento aggiornato.")
                    st.rerun()
                if delete:
                    _safe_backup("prima_elimina_pagamento")
                    session.delete(pagamento)
                    session.commit()
                    st.rerun()
    else:
        st.info("Nessun pagamento registrato.")

    st.markdown("---")
    st.subheader("Nuovo importo / pagamento")
    st.caption(
        "Quando arriva il decreto di liquidazione finale, registra una riga di tipo 'saldo' "
        "con imponibile e spese ancora dovuti dopo avere detratto l'acconto. "
        "La cassa previdenziale 4% sull'imponibile e la marca da bollo da 2 euro vengono calcolate automaticamente. "
        "Lascia 'Importo ricevuto' a 0 finche' il pagamento non viene materialmente incassato."
    )
    with st.form(f"{prefix}_nuovo_pagamento_{inc.id}", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            tipo = st.selectbox("Tipo", TIPI_PAGAMENTO, key=f"{prefix}_new_pag_tipo_{inc.id}")
            descrizione = st.text_input(
                "Descrizione",
                placeholder="Esempio: acconto da decreto di nomina o saldo da decreto di liquidazione",
                key=f"{prefix}_new_pag_desc_{inc.id}",
            )
            imponibile = st.number_input(
                "Imponibile",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.2f",
                key=f"{prefix}_new_pag_imponibile_{inc.id}",
            )
            spese = st.number_input(
                "Spese liquidate",
                min_value=0.0,
                value=0.0,
                step=50.0,
                format="%.2f",
                key=f"{prefix}_new_pag_spese_{inc.id}",
            )
            calcolo = calcola_totale_fattura(imponibile, spese)
            importo_dovuto_manual = st.number_input(
                "Dovuto manuale se non usi imponibile/spese",
                help="Usato solo se imponibile e spese sono entrambi a 0.",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.2f",
                key=f"{prefix}_new_pag_dovuto_manual_{inc.id}",
            )
            st.caption(
                "Cassa 4%: "
                f"{fmt_euro(calcolo['cassa'])} | Bollo: {fmt_euro(calcolo['bollo'])} | "
                f"Totale da incassare: {fmt_euro(calcolo['totale'])}"
            )
            data_riferimento = st.date_input(
                "Data decreto / mandato",
                value=None,
                key=f"{prefix}_new_pag_data_rif_{inc.id}",
            )
        with c2:
            importo_ricevuto = st.number_input(
                "Importo ricevuto",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.2f",
                key=f"{prefix}_new_pag_ricevuto_{inc.id}",
            )
            data_pagamento = st.date_input(
                "Data pagamento",
                value=None,
                key=f"{prefix}_new_pag_data_pag_{inc.id}",
            )
            pagatore = st.text_input("Pagatore", key=f"{prefix}_new_pag_pagatore_{inc.id}")
            note = st.text_area("Note", height=80, key=f"{prefix}_new_pag_note_{inc.id}")
        if st.form_submit_button("Aggiungi pagamento", type="primary"):
            pagamento = Pagamento(
                incarico_id=inc.id,
                tipo=tipo,
                descrizione=descrizione or None,
                imponibile=imponibile,
                spese=spese,
                importo_dovuto=calcolo["totale"] if imponibile or spese else importo_dovuto_manual,
                importo_ricevuto=importo_ricevuto,
                data_riferimento=data_riferimento or None,
                data_pagamento=data_pagamento or None,
                pagatore=pagatore or None,
                note=note or None,
            )
            session.add(pagamento)
            session.commit()
            st.success("Importo / pagamento aggiunto.")
            st.rerun()


def _render_controlli_incarico(session, inc, prefix: str):
    incongruenze = rileva_incongruenze_incarico(inc)
    problemi = [voce for voce in incongruenze if voce.livello in {"errore", "avviso"}]
    if not incongruenze:
        st.success("Termini, Eventi e sequenza delle scadenze risultano coerenti.")
    else:
        if problemi:
            st.warning(f"Rilevate {len(problemi)} anomalie da verificare.")
        else:
            st.info("Sono presenti solo differenze storiche che non influenzano la dashboard.")
        st.dataframe(pd.DataFrame([{
            "Livello": voce.livello,
            "Controllo": voce.codice,
            "Descrizione": voce.descrizione,
            "Termine ID": voce.termine_id or "-",
            "Evento ID": voce.evento_id or "-",
        } for voce in incongruenze]), hide_index=True, use_container_width=True)

    st.caption(
        "La sincronizzazione crea o riallinea soltanto gli Eventi collegati ai Termini. "
        "Gli eventi autonomi e quelli importati restano invariati."
    )
    if st.button("Sincronizza Eventi collegati", type="primary", key=f"{prefix}_sync_{inc.id}"):
        aggiornati = 0
        for termine in inc.termini:
            if sincronizza_evento_da_termine(session, inc, termine) is not None:
                aggiornati += 1
        session.commit()
        st.success(f"Sincronizzati {aggiornati} Termini con i rispettivi Eventi.")
        st.rerun()


# ------------------------- pagine -------------------------

def page_dashboard():
    st.title("Dashboard scadenziario")
    session = get_session()
    incarichi = (
        session.query(Incarico)
        .options(
            selectinload(Incarico.termini),
            selectinload(Incarico.eventi),
            selectinload(Incarico.sospensioni),
        )
        .all()
    )

    # Avviso e gestione dati demo
    n_demo = sum(1 for i in incarichi if i.origine_dato == "demo")
    if n_demo and not OFFLINE_MODE:
        st.warning(f"Sono presenti {n_demo} dati demo nel database.")
        with st.expander("Amministrazione dati demo"):
            confirm = st.checkbox("Confermo eliminazione dati demo", key="confirm_demo_del")
            if st.button("Elimina dati demo", disabled=not confirm, type="secondary"):
                _safe_backup("prima_elimina_demo")
                eliminati = elimina_dati_demo(session)
                st.success(f"Eliminati {eliminati} incarichi demo.")
                st.rerun()

    if not OFFLINE_MODE:
        with st.expander("Amministrazione incarichi"):
            if incarichi:
                options = {
                    f"{i.tipo} {i.numero_rg} - {i.tribunale}": i.id
                    for i in incarichi
                }
                incarico_da_eliminare = st.selectbox(
                    "Seleziona incarico da eliminare",
                    list(options.keys()),
                    key="delete_incarico_select",
                )
                confirm_delete = st.checkbox(
                    "Confermo eliminazione incarico e dati collegati",
                    key="confirm_incarico_del",
                )
                if st.button(
                    "Elimina incarico",
                    disabled=not confirm_delete,
                    type="secondary",
                ):
                    _safe_backup("prima_elimina_incarico")
                    eliminato = elimina_incarico(session, options[incarico_da_eliminare])
                    if eliminato:
                        st.success("Incarico eliminato.")
                    else:
                        st.warning("Incarico non trovato.")
                    st.rerun()

    if not incarichi:
        st.info("Nessun incarico presente. Inizia da 'Nuovo incarico'.")
        return

    rows = []
    oggi_dashboard = date.today()
    for inc in incarichi:
        prossima = trova_prossima_attivita_dashboard(inc, oggi_dashboard)
        alert = classifica_per_dashboard(inc.stato, prossima)
        metric_key = metric_key_dashboard(inc.stato, alert)
        waiting_visible = attesa_osservazioni_da_mostrare_dashboard(inc, oggi_dashboard)
        incarico_label = f"{inc.tipo} {inc.numero_rg}"
        note_full = inc.note or ""
        search_blob = " ".join(
            str(x or "")
            for x in (
                inc.tipo,
                inc.numero_rg,
                inc.tribunale,
                inc.giudice,
                inc.parti,
                inc.oggetto,
                note_full,
                prossima.tipo_termine if prossima else "",
            )
        ).lower()

        rows.append({
            "id": inc.id,
            "Incarico": (
                f"<a href='?page={'Consulta%20incarico' if OFFLINE_MODE else 'Modifica%20incarico'}&incarico_id={inc.id}' "
                f"style='color:#1565c0;text-decoration:none;font-weight:600'>"
                f"{escape(incarico_label)}</a>"
                f"<br><a class='mobile-open-link' "
                f"href='?page={'Consulta%20incarico' if OFFLINE_MODE else 'Modifica%20incarico'}&incarico_id={inc.id}'>"
                "Apri incarico</a>"
            ),
            "Ufficio": escape(inc.tribunale or ""),
            "Stato": escape(inc.stato or ""),
            "Priorita": escape(inc.priorita or "media"),
            "Prossima scadenza": fmt_date(prossima.data_scadenza) if prossima else "-",
            "Tipo termine": escape(prossima.tipo_termine if prossima else "da definire"),
            "Giorni residui": prossima.giorni_residui if prossima else None,
            "alert_raw": alert,
            "metric_raw": metric_key,
            "waiting_visible": waiting_visible,
            "Note": escape(note_full[:140]),
            "search_blob": search_blob,
        })

    metric_keys = [
        "scaduto",
        "critico",
        "urgente",
        "pianificare",
        "dati_mancanti",
        "regolare",
        "attesa_osservazioni",
        "sospeso",
        "chiuso",
    ]
    with st.expander("Filtri dashboard"):
        q = st.text_input(
            "Cerca",
            placeholder="Numero procedura, ufficio, parti, oggetto, note...",
            key="dash_search",
        ).strip().lower()
        f1, f2, f3 = st.columns(3)
        alert_filter = f1.multiselect(
            "Alert",
            metric_keys,
            format_func=lambda key: ALERT_LABEL.get(key, key),
            key="dash_alert_filter",
        )
        stato_filter = f2.multiselect("Stato", STATI_INCARICO, key="dash_stato_filter")
        prio_filter = f3.multiselect("Priorita", PRIORITA, key="dash_prio_filter")
        show_waiting = st.checkbox("Mostra attesa osservazioni", value=False, key="dash_show_waiting")
        show_closed = st.checkbox("Mostra incarichi chiusi", value=True, key="dash_show_closed")

    if q:
        rows = [r for r in rows if q in r["search_blob"]]
    if alert_filter:
        rows = [r for r in rows if r["metric_raw"] in alert_filter]
    if stato_filter:
        rows = [r for r in rows if r["Stato"] in stato_filter]
    if prio_filter:
        rows = [r for r in rows if r["Priorita"] in prio_filter]

    counter_rows = list(rows)

    if not show_waiting and "attesa_osservazioni" not in alert_filter:
        rows = [
            r for r in rows
            if r["metric_raw"] != "attesa_osservazioni" or r["waiting_visible"]
        ]
    if not show_closed:
        rows = [r for r in rows if r["metric_raw"] != "chiuso" and r["Stato"] != "chiuso"]

    rows.sort(key=lambda r: (ALERT_PRIORITY.get(r["alert_raw"], 99),
                             r["Giorni residui"] if r["Giorni residui"] is not None else 9999))

    counters = {}
    for r in counter_rows:
        counters[r["metric_raw"]] = counters.get(r["metric_raw"], 0) + 1

    cols = st.columns(len(metric_keys))
    for i, key in enumerate(metric_keys):
        cols[i].metric(ALERT_LABEL[key], counters.get(key, 0))

    st.caption(f"Incarichi visualizzati: {len(rows)} su {len(incarichi)}")
    st.markdown("---")

    st.markdown("---")

    html = ['<div class="dashboard-table-wrap"><table class="dashboard-table">']
    html.append(
        "<colgroup>"
        "<col style='width:18%'>"
        "<col style='width:11%'>"
        "<col style='width:7%'>"
        "<col style='width:7%'>"
        "<col style='width:12%'>"
        "<col style='width:9%'>"
        "<col style='width:5%'>"
        "<col style='width:10%'>"
        "<col style='width:21%'>"
        "</colgroup>"
        "<thead><tr>"
        "<th>Incarico</th>"
        "<th>Ufficio</th>"
        "<th>Stato</th>"
        "<th>Prio.</th>"
        "<th>Prossima attivita</th>"
        "<th>Tipo</th>"
        "<th>gg</th>"
        "<th>Alert</th>"
        "<th>Note</th>"
        "</tr></thead><tbody>"
    )
    for r in rows:
        gg = r["Giorni residui"]
        gg_disp = "-" if gg is None else str(gg)
        html.append(
            f"<tr>"
            f"<td data-label='Incarico'>{r['Incarico']}</td>"
            f"<td data-label='Ufficio'>{r['Ufficio']}</td>"
            f"<td data-label='Stato'>{r['Stato']}</td>"
            f"<td data-label='Priorita'>{r['Priorita']}</td>"
            f"<td data-label='Prossima'>{r['Prossima scadenza']}</td>"
            f"<td data-label='Tipo'>{r['Tipo termine']}</td>"
            f"<td data-label='Giorni' class='cell-number'>{gg_disp}</td>"
            f"<td data-label='Alert'>{alert_badge_html(r['alert_raw'])}</td>"
            f"<td data-label='Note' class='cell-muted'>{r['Note']}</td>"
            f"</tr>"
        )
    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    session.close()


def page_nuovo_incarico():
    st.title("Nuovo incarico")
    session = get_session()

    with st.form("nuovo_incarico", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            tipo = st.selectbox("Tipo incarico", TIPI_INCARICO)
            numero_rg = st.text_input("Numero procedura *")
            tribunale = st.text_input("Ufficio *")
            giudice = st.text_input("Giudice / PM / Responsabile")
            parti = st.text_area("Parti", height=70)
            oggetto = st.text_area("Descrizione / Oggetto", height=70)
        with c2:
            data_conferimento = st.date_input("Data nomina *", value=date.today())
            data_giuramento = st.date_input("Data giuramento", value=None)
            data_inizio_operazioni = st.date_input("Data inizio operazioni", value=None)
            stato = st.selectbox("Stato", STATI_INCARICO)
            priorita = st.selectbox("Priorita", PRIORITA, index=1)
            note = st.text_area("Note", height=70)

        submitted = st.form_submit_button("Crea incarico", type="primary")
        if submitted:
            if not numero_rg or not tribunale:
                st.error("Numero procedura e Ufficio sono obbligatori.")
            else:
                inc = Incarico(
                    tipo=tipo,
                    numero_rg=numero_rg.strip(),
                    tribunale=tribunale.strip(),
                    giudice=giudice or None,
                    parti=parti or None,
                    oggetto=oggetto or None,
                    data_conferimento=data_conferimento,
                    data_giuramento=data_giuramento or None,
                    data_inizio_operazioni=data_inizio_operazioni or None,
                    stato=stato,
                    priorita=priorita,
                    origine_dato="manuale",
                    note=note or None,
                )
                session.add(inc)
                session.commit()
                st.success(f"Incarico {tipo} {numero_rg} creato.")
    session.close()


def page_termini():
    st.title("Gestione termini")
    session = get_session()

    inc = _select_incarico(session, key="termini_inc")
    if inc is None:
        session.close()
        return

    st.subheader(f"Termini di {inc.tipo} {inc.numero_rg}")
    _render_termini_editor(session, inc, "termini")
    session.close()


def page_eventi():
    st.title("Eventi e scadenze")
    session = get_session()

    inc = _select_incarico(session, key="eventi_inc")
    if inc is None:
        session.close()
        return

    st.subheader(f"{inc.tipo} {inc.numero_rg} - {inc.tribunale}")

    tab1, tab2 = st.tabs(["Scadenze calcolate", "Eventi manuali"])

    with tab1:
        eventi_calc = genera_eventi_standard(inc, inc.termini)
        if not eventi_calc:
            st.info("Nessun termine attivo per cui calcolare scadenze.")
        else:
            for sc in sorted(eventi_calc, key=lambda e: e.data_scadenza):
                # Trova il termine di origine per il toggle completato
                termine = next(
                    (t for t in inc.termini
                     if t.id == sc.termine_id),
                    None,
                )
                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                col1.markdown(
                    f"**{sc.tipo_termine}** - {fmt_date(sc.data_scadenza)} "
                    f"({sc.giorni_residui:+d} gg)"
                )
                col2.markdown(alert_badge_html(sc.alert), unsafe_allow_html=True)
                col3.write("Completato" if sc.completato else "In corso")
                if not sc.completato and termine:
                    if col4.button("Marca completato", key=f"compl_{termine.id}"):
                        termine.completato = True
                        sincronizza_evento_da_termine(session, inc, termine)
                        session.commit()
                        st.rerun()

    with tab2:
        eventi_manuali = [e for e in inc.eventi if not getattr(e, "annullato", False)]
        if eventi_manuali:
            rows = []
            for e in eventi_manuali:
                rows.append({
                    "ID": e.id,
                    "Tipo": e.tipo,
                    "Data": fmt_date(e.data),
                    "Ora": e.ora or "-",
                    "Luogo": e.luogo or "-",
                    "Descrizione": (e.descrizione or "")[:80],
                    "Completato": "si" if e.completato else "no",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            with st.expander("Azioni su evento"):
                ids = [e.id for e in eventi_manuali]
                sel = st.selectbox("ID evento", ids, key="ev_action")
                ev = session.get(Evento, sel)
                c1, c2 = st.columns(2)
                if c1.button("Toggle completato", key="ev_compl"):
                    ev.completato = not ev.completato
                    session.commit()
                    st.rerun()
                if c2.button("Annulla evento", type="secondary"):
                    _safe_backup("prima_annulla_evento")
                    ev.annullato = True
                    session.commit()
                    st.rerun()
        else:
            st.info("Nessun evento manuale.")

        st.markdown("---")
        st.subheader("Nuovo evento manuale")
        with st.form("nuovo_evento", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                tipo_e = st.selectbox("Tipo", TIPI_EVENTO)
                data_e = st.date_input("Data", value=date.today())
                ora_e = st.text_input("Ora (HH:MM)")
            with c2:
                luogo_e = st.text_input("Luogo")
                descr_e = st.text_area("Descrizione", height=80)
            if st.form_submit_button("Aggiungi evento", type="primary"):
                ev = Evento(
                    incarico_id=inc.id,
                    tipo=tipo_e,
                    data=data_e,
                    ora=ora_e or None,
                    luogo=luogo_e or None,
                    descrizione=descr_e or None,
                )
                session.add(ev)
                session.commit()
                st.success("Evento aggiunto.")
                st.rerun()

    session.close()


def page_sospensioni():
    st.title("Sospensioni")
    session = get_session()

    inc = _select_incarico(session, key="sosp_inc")
    if inc is None:
        session.close()
        return

    st.subheader(f"{inc.tipo} {inc.numero_rg}")

    if inc.sospensioni:
        rows = []
        for s in inc.sospensioni:
            rows.append({
                "ID": s.id,
                "Inizio": fmt_date(s.data_inizio),
                "Fine": fmt_date(s.data_fine),
                "Incide": "si" if s.incide_su_scadenze else "no",
                "Motivo": (s.motivo or "")[:80],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        with st.expander("Elimina sospensione"):
            ids = [s.id for s in inc.sospensioni]
            sel = st.selectbox("ID", ids, key="sosp_del")
            if st.button("Elimina", type="secondary"):
                _safe_backup("prima_elimina_sospensione")
                s = session.get(Sospensione, sel)
                session.delete(s)
                session.flush()
                session.expire(inc, ["sospensioni"])
                ricalcola_termini_incarico(session, inc, "Eliminazione sospensione")
                session.commit()
                st.rerun()
    else:
        st.info("Nessuna sospensione registrata.")

    st.markdown("---")
    st.subheader("Nuova sospensione")
    with st.form("nuova_sosp", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            di = st.date_input("Data sospensione *", value=date.today())
            df = st.date_input("Data ripresa", value=None)
        with c2:
            incide = st.checkbox("Incide sulle scadenze", value=True)
            motivo = st.text_area("Note / motivo", height=80)
        if st.form_submit_button("Aggiungi sospensione", type="primary"):
            if df and df < di:
                st.error("La data di ripresa non può precedere la data di sospensione.")
                session.close()
                return
            s = Sospensione(
                incarico_id=inc.id,
                data_inizio=di,
                data_fine=df or None,
                motivo=motivo or None,
                incide_su_scadenze=incide,
            )
            session.add(s)
            session.flush()
            session.expire(inc, ["sospensioni"])
            ricalcola_termini_incarico(session, inc, "Nuova sospensione")
            session.commit()
            st.success("Sospensione aggiunta.")
            st.rerun()

    session.close()


def _render_verifica_import_incarico(session, inc):
    flag = " - DA CORREGGERE" if is_numero_da_correggere(inc.numero_rg) else ""

    with st.expander(f"{inc.tipo} {inc.numero_rg}{flag} | {inc.tribunale}"):
        with st.form(f"inc_form_{inc.id}"):
            c1, c2 = st.columns(2)
            with c1:
                new_numero = st.text_input("Numero procedura", value=inc.numero_rg or "")
                new_tipo = st.selectbox(
                    "Tipo incarico", TIPI_INCARICO,
                    index=TIPI_INCARICO.index(inc.tipo) if inc.tipo in TIPI_INCARICO else 0,
                )
                new_tribunale = st.text_input("Ufficio", value=inc.tribunale or "")
                new_priorita = st.selectbox(
                    "Priorita", PRIORITA,
                    index=PRIORITA.index(inc.priorita) if inc.priorita in PRIORITA else 1,
                )
            with c2:
                new_stato = st.selectbox(
                    "Stato", STATI_INCARICO,
                    index=STATI_INCARICO.index(inc.stato) if inc.stato in STATI_INCARICO else 0,
                )
                new_oggetto = st.text_area("Oggetto / descrizione", value=inc.oggetto or "", height=80)
                new_note = st.text_area("Note", value=inc.note or "", height=80)
            if st.form_submit_button("Salva incarico", type="primary"):
                inc.numero_rg = new_numero.strip()
                inc.tipo = new_tipo
                inc.tribunale = new_tribunale.strip()
                inc.priorita = new_priorita
                inc.stato = new_stato
                inc.oggetto = new_oggetto or None
                inc.note = new_note or None
                session.commit()
                st.success("Incarico aggiornato.")
                st.rerun()

        if inc.eventi:
            st.markdown("**Eventi associati**")
            for ev in inc.eventi:
                if ev.annullato:
                    continue
                with st.form(f"ev_form_{ev.id}"):
                    c1, c2, c3 = st.columns([2, 2, 3])
                    with c1:
                        new_tipo_e = st.selectbox(
                            "Tipo evento", TIPI_EVENTO,
                            index=TIPI_EVENTO.index(ev.tipo) if ev.tipo in TIPI_EVENTO else 0,
                            key=f"tipo_{ev.id}",
                        )
                        new_data = st.date_input(
                            "Data prevista",
                            value=ev.data,
                            key=f"data_{ev.id}",
                        )
                    with c2:
                        new_stato_e = st.selectbox(
                            "Stato evento", STATI_EVENTO,
                            index=STATI_EVENTO.index(stato_evento(ev)),
                            key=f"stato_{ev.id}",
                        )
                    with c3:
                        new_descr = st.text_area(
                            "Note evento",
                            value=ev.descrizione or "",
                            height=80,
                            key=f"descr_{ev.id}",
                        )
                    c4, c5 = st.columns(2)
                    save = c4.form_submit_button("Salva evento")
                    delete = c5.form_submit_button("Annulla evento", type="secondary")
                    if save:
                        ev.tipo = new_tipo_e
                        ev.data = new_data or None
                        applica_stato_evento(ev, new_stato_e)
                        ev.descrizione = new_descr or None
                        session.commit()
                        st.success("Evento aggiornato.")
                        st.rerun()
                    if delete:
                        ev.annullato = True
                        session.commit()
                        st.rerun()
        else:
            st.caption("Nessun evento associato.")


def page_verifica_import():
    st.title("Verifica import Excel")
    session = get_session()
    incs = (
        session.query(Incarico)
        .options(selectinload(Incarico.eventi))
        .filter(Incarico.origine_dato == "import_excel")
        .order_by(Incarico.id)
        .all()
    )
    if not incs:
        st.info("Nessun incarico importato da Excel.")
        session.close()
        return

    da_correggere = [i for i in incs if is_numero_da_correggere(i.numero_rg)]
    if da_correggere:
        st.warning(
            f"{len(da_correggere)} incarichi con numero generico (es. IMPORT-*) "
            "richiedono correzione manuale."
        )

    for inc in incs:
        _render_verifica_import_incarico(session, inc)

    session.close()


def page_controllo_operativo():
    st.title("Controllo operativo")
    session = get_session()
    try:
        voci = genera_voci_monitoraggio(session)
        fonte = etichetta_fonte_database()
        st.caption(f"Fonte dati: {fonte} | aggiornamento: {date.today():%d/%m/%Y}")

        categorie = [
            "scaduto",
            "riattivare",
            "critico",
            "urgente",
            "pianificare",
            "dati_mancanti",
            "anomalia",
            "pagamento",
        ]
        conteggi = {categoria: 0 for categoria in categorie}
        for voce in voci:
            conteggi[voce.categoria] = conteggi.get(voce.categoria, 0) + 1

        metriche = st.columns(4)
        metriche[0].metric("Scaduti / da riattivare", conteggi["scaduto"] + conteggi["riattivare"])
        metriche[1].metric("Critici / urgenti", conteggi["critico"] + conteggi["urgente"])
        metriche[2].metric("Da pianificare", conteggi["pianificare"])
        metriche[3].metric("Pagamenti sospesi", conteggi["pagamento"])

        if not voci:
            st.success("Nessuna scadenza o anomalia operativa da segnalare.")
            return

        st.dataframe(
            pd.DataFrame([{
                "Priorita": voce.categoria,
                "Incarico": voce.incarico,
                "Attivita": voce.attivita,
                "Data": fmt_date(voce.data),
                "gg": voce.giorni if voce.giorni is not None else "-",
                "Azione consigliata": voce.azione,
                "Dettaglio": voce.dettaglio,
            } for voce in voci]),
            hide_index=True,
            use_container_width=True,
        )
    finally:
        session.close()


def page_modifica_incarico():
    st.title("Modifica incarico")
    session = get_session()

    inc = None
    incarico_id = st.query_params.get("incarico_id")
    if incarico_id is not None:
        try:
            inc = session.get(Incarico, int(incarico_id))
        except (TypeError, ValueError):
            inc = None

    if inc is None:
        inc = _select_incarico(session, key="modifica_inc")
    if inc is None:
        session.close()
        return
    st.subheader(f"{inc.tipo} {inc.numero_rg} - {inc.tribunale}")

    sezioni = [
        "Dati",
        "Termini",
        "Eventi",
        "Sospensioni",
        "Documenti",
        "Pagamenti",
        "Controlli",
    ]
    sezione = st.segmented_control(
        "Sezione incarico",
        sezioni,
        default="Dati",
        key=f"edit_section_{inc.id}",
        label_visibility="collapsed",
    )

    if sezione == "Dati":
        _render_incarico_editor(session, inc, "edit")
    elif sezione == "Termini":
        _render_termini_editor(session, inc, "edit_terms")
    elif sezione == "Eventi":
        _render_eventi_editor(session, inc, "edit_events")
    elif sezione == "Sospensioni":
        _render_sospensioni_editor(session, inc, "edit_sosp")
    elif sezione == "Documenti":
        _render_documenti_editor(session, inc, "edit_docs")
    elif sezione == "Pagamenti":
        _render_pagamenti_editor(session, inc, "edit_pag")
    elif sezione == "Controlli":
        _render_controlli_incarico(session, inc, "edit_check")
    session.close()


def page_consulta_incarico():
    st.title("Consulta incarico")
    session = get_session()
    try:
        inc = None
        incarico_id = st.query_params.get("incarico_id")
        if incarico_id is not None:
            try:
                inc = session.get(Incarico, int(incarico_id))
            except (TypeError, ValueError):
                inc = None
        if inc is None:
            inc = _select_incarico(session, key="consulta_inc")
        if inc is None:
            return

        st.subheader(f"{inc.tipo} {inc.numero_rg} - {inc.tribunale}")
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Numero procedura", value=inc.numero_rg or "", disabled=True)
            st.text_input("Tipo incarico", value=inc.tipo or "", disabled=True)
            st.text_input("Ufficio", value=inc.tribunale or "", disabled=True)
            st.text_input("Priorita", value=inc.priorita or "", disabled=True)
        with c2:
            st.text_input("Stato", value=inc.stato or "", disabled=True)
            st.text_area("Oggetto / descrizione", value=inc.oggetto or "", disabled=True)
            st.text_area("Note", value=inc.note or "", disabled=True)

        tabs = st.tabs(["Termini", "Eventi", "Sospensioni", "Documenti", "Pagamenti"])
        with tabs[0]:
            st.dataframe(pd.DataFrame([{
                "Tipo": t.tipo_termine,
                "Scadenza": fmt_date(calcola_scadenza_termine(inc, t)),
                "Giorni": t.giorni,
                "Attivo": t.attivo,
                "Completato": t.completato,
                "Note": t.note or "",
            } for t in _termini_in_ordine_cronologico(inc)]), use_container_width=True, hide_index=True)
        with tabs[1]:
            st.dataframe(pd.DataFrame([{
                "Tipo": e.tipo,
                "Data": fmt_date(e.data),
                "Ora": e.ora or "",
                "Stato": stato_evento(e),
                "Descrizione": e.descrizione or "",
            } for e in inc.eventi]), use_container_width=True, hide_index=True)
        with tabs[2]:
            st.dataframe(pd.DataFrame([{
                "Inizio": fmt_date(s.data_inizio),
                "Fine": fmt_date(s.data_fine),
                "Incide sulle scadenze": s.incide_su_scadenze,
                "Motivo": s.motivo or "",
            } for s in inc.sospensioni]), use_container_width=True, hide_index=True)
        with tabs[3]:
            st.dataframe(pd.DataFrame([{
                "Nome": d.nome,
                "Tipo": d.tipo or "",
                "Data": fmt_date(d.data_documento),
                "Note": d.note or "",
            } for d in inc.documenti]), use_container_width=True, hide_index=True)
        with tabs[4]:
            riepilogo = riepilogo_pagamenti(inc.pagamenti)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Dovuto/liquidato", fmt_euro(riepilogo["totale_dovuto"]))
            c2.metric("Acconti ricevuti", fmt_euro(riepilogo["acconti_ricevuti"]))
            c3.metric("Totale ricevuto", fmt_euro(riepilogo["totale_ricevuto"]))
            c4.metric("Sospeso/residuo", fmt_euro(riepilogo["residuo"]))
            st.dataframe(pd.DataFrame([{
                "Tipo": p.tipo,
                "Descrizione": p.descrizione or "",
                "Imponibile": fmt_euro(p.imponibile),
                "Spese": fmt_euro(p.spese),
                "Dovuto da incassare": fmt_euro(importo_dovuto_pagamento(p)),
                "Ricevuto": fmt_euro(p.importo_ricevuto),
                "Data rif.": fmt_date(p.data_riferimento),
                "Data pagamento": fmt_date(p.data_pagamento),
                "Pagatore": p.pagatore or "",
                "Note": p.note or "",
            } for p in inc.pagamenti]), use_container_width=True, hide_index=True)
    finally:
        session.close()


def page_import_excel():
    st.title("Import da Excel")
    st.caption(
        "Carica un file `.xlsx` con il layout dello scadenziario originario "
        "(A=descrizione, B=nomina, C=giuramento, D=inizio op., E=bozza, F=osservazioni, "
        "G=deposito, H=udienza, I=stato, K=note, L=sospensione, M=ripresa, N=gg sosp.). "
        "La colonna J (giorni alla scadenza) viene ignorata perché ricalcolata."
    )

    with st.expander("Istruzioni per preparare il file Excel"):
        st.markdown(
            """
            - Usa un file `.xlsx` con gli incarichi in una tabella continua, senza righe vuote tra un record e l'altro.
            - Mantieni l'intestazione nella prima riga e lascia partire i dati dalla riga 2, salvo eccezioni.
            - Rispetta questo ordine colonne: A descrizione, B nomina, C giuramento, D inizio operazioni, E bozza, F osservazioni, G deposito, H udienza, I stato, K note, L sospensione, M ripresa, N giorni sospensione.
            - La colonna J non va compilata per l'import: viene ignorata e i giorni residui sono ricalcolati dall'app.
            - Inserisci le date come vere date Excel oppure come testo chiaro, ad esempio `01/03/2026`.
            - Evita celle unite, formule poco leggibili o testi ambigui nelle colonne data.
            - Se il numero procedura non è riconoscibile nella descrizione, l'app assegna un codice provvisorio `IMPORT-n`.
            - Se l'ufficio o tribunale non è ricavabile dalla descrizione, l'incarico viene importato con ufficio `(da definire)`.
            - Se il file ha più fogli, puoi indicare il nome del foglio qui sotto; se lasci vuoto, viene usato il primo.
            """
        )

    uploaded = st.file_uploader("Seleziona file Excel", type=["xlsx", "xlsm"])
    c1, c2 = st.columns(2)
    sheet_name = c1.text_input("Nome foglio (vuoto = primo foglio)")
    start_row = c2.number_input("Riga di partenza", min_value=1, value=2, step=1)

    if uploaded is None:
        return

    if st.button("Avvia importazione", type="primary"):
        try:
            _safe_backup("prima_import_excel")
            report = importa_excel(
                uploaded,
                sheet_name=sheet_name.strip() or None,
                start_row=int(start_row),
            )
        except Exception as exc:
            st.error(f"Errore: {exc!r}")
            return

        st.success(
            f"Importazione completata: {report['imported']} righe importate, "
            f"{report['skipped']} saltate."
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Importate", report["imported"])
        c2.metric("Saltate (A vuota)", report["skipped"])
        c3.metric("Anomalie", len(report["anomalies"]) + len(report["date_errors"]))

        if report["date_errors"]:
            with st.expander(f"Date non riconosciute ({len(report['date_errors'])})", expanded=False):
                for msg in report["date_errors"]:
                    st.write(f"- {msg}")

        if report["anomalies"]:
            with st.expander(f"Anomalie ({len(report['anomalies'])})", expanded=False):
                for msg in report["anomalies"]:
                    st.write(f"- {msg}")


def page_export_excel():
    st.title("Esporta Excel")
    session = get_session()

    incarichi_count = session.query(Incarico).count()
    st.caption(
        "Genera un file `.xlsx` con incarichi, termini, eventi, sospensioni, documenti e pagamenti "
        "presenti nel database locale."
    )
    st.metric("Incarichi esportabili", incarichi_count)

    if st.button("Prepara export Excel", type="primary"):
        with st.spinner("Preparazione del file Excel..."):
            st.session_state["export_excel_data"] = genera_excel_export(session)
            st.session_state["export_excel_date"] = date.today()

    data = st.session_state.get("export_excel_data")
    if data is not None:
        export_date = st.session_state.get("export_excel_date", date.today())
        st.download_button(
            "Scarica export Excel",
            data=data,
            file_name=f"scadenziario_ctu_export_{export_date:%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        st.caption("Premi nuovamente 'Prepara export Excel' per includere modifiche successive.")

    session.close()


# ------------------------- router -------------------------

PAGES = {
    "Dashboard": page_dashboard,
    "Controllo operativo": page_controllo_operativo,
    "Modifica incarico": page_modifica_incarico,
    "Nuovo incarico": page_nuovo_incarico,
    "Eventi": page_eventi,
    "Sospensioni": page_sospensioni,
    "Import Excel": page_import_excel,
    "Esporta Excel": page_export_excel,
    "Verifica import": page_verifica_import,
}

if OFFLINE_MODE:
    PAGES = {
        "Dashboard": page_dashboard,
        "Controllo operativo": page_controllo_operativo,
        "Consulta incarico": page_consulta_incarico,
        "Esporta Excel": page_export_excel,
    }

requested_page = st.query_params.get("page", "Dashboard")
if requested_page == "Gestione termini":
    requested_page = "Modifica incarico"
if requested_page not in PAGES:
    requested_page = "Dashboard"

with st.sidebar:
    st.markdown("### Scadenziario CTU Pro")
    page_names = list(PAGES.keys())
    scelta = st.radio(
        "Navigazione",
        page_names,
        index=page_names.index(requested_page),
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("Legenda alert")
    for label, color in ALERT_COLORS.items():
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:6px;font-size:0.85em'>"
            f"<span style='display:inline-block;width:12px;height:12px;background:{color};"
            f"border-radius:2px'></span>{label}</div>",
            unsafe_allow_html=True,
        )

if scelta != requested_page:
    st.query_params["page"] = scelta
    if scelta not in ("Modifica incarico", "Consulta incarico") and "incarico_id" in st.query_params:
        del st.query_params["incarico_id"]
    st.rerun()

PAGES[scelta]()


