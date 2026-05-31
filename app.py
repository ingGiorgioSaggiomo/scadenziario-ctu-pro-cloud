"""Scadenziario CTU Pro â€” Interfaccia Streamlit."""

import os
from datetime import date
from html import escape

import pandas as pd
import streamlit as st

from src.database import elimina_dati_demo, elimina_incarico, get_session, init_db
from src.backup_tools import crea_backup_database
from src.deadline_engine import genera_eventi_standard
from src.export_tools import genera_excel_export
from src.import_excel import importa_excel
from src.models import Documento, Evento, Incarico, Sospensione, Termine
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
    applica_stato_evento,
    calcola_scadenza_termine,
    classifica_per_dashboard,
    fmt_date,
    is_numero_da_correggere,
    stato_evento,
    trova_prossima_attivita_dashboard,
)

def check_password() -> bool:
    """Restituisce True se l'utente ha inserito la password corretta."""
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


init_db()

st.set_page_config(page_title="Scadenziario CTU Pro", layout="wide", page_icon=None)

# Controllo della password per accessi online
if not check_password():
    st.stop()

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    h1 {font-size: 1.7rem !important; margin-bottom: 0.5rem;}
    h2 {font-size: 1.3rem !important; margin-top: 1rem;}
    div[data-testid="stMetric"] {background:#f5f5f5; padding:0.5rem 0.8rem; border-radius:6px;}
    .dashboard-table-wrap {width:100%; overflow-x:auto;}
    .dashboard-table {width:100%; border-collapse:collapse; table-layout:fixed;}
    .dashboard-table th {
        padding:8px;
        background:#eceff1;
        text-align:left;
        overflow-wrap:anywhere;
    }
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
        .block-container {
            padding-left:0.75rem;
            padding-right:0.75rem;
            padding-top:0.75rem;
        }
        h1 {font-size:1.35rem !important;}
        h2 {font-size:1.15rem !important;}
        h3 {font-size:1rem !important;}
        div[data-testid="stMetric"] {
            padding:0.45rem 0.55rem;
            min-height:68px;
        }
        div[data-testid="stMetricLabel"] p {font-size:0.72rem;}
        div[data-testid="stMetricValue"] {font-size:1.25rem;}
        .dashboard-table-wrap {overflow-x:visible;}
        .dashboard-table,
        .dashboard-table tbody,
        .dashboard-table tr,
        .dashboard-table td {
            display:block;
            width:100%;
        }
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


# ------------------------- helpers -------------------------

def _select_incarico(session, label="Incarico", key=None):
    incarichi = session.query(Incarico).order_by(Incarico.data_conferimento.desc()).all()
    if not incarichi:
        st.info("Nessun incarico presente. Crea un incarico dalla pagina 'Nuovo incarico'.")
        return None
    options = {f"{i.tipo} {i.numero_rg} â€” {i.tribunale}": i for i in incarichi}
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
            inc.stato = "attesa osservazioni"
            session.commit()
            st.success("Stato aggiornato in attesa osservazioni.")
            st.rerun()
    elif inc.stato == "attesa osservazioni":
        st.info("Questo incarico e' in attesa delle osservazioni alla bozza; non viene mostrato tra i lavori immediati della dashboard.")


def _render_termini_editor(session, inc, prefix: str):
    if inc.termini:
        rows = []
        for t in inc.termini:
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
            ids = [t.id for t in inc.termini]
            sel = st.selectbox("Seleziona ID", ids, key=f"{prefix}_termine_action_{inc.id}")
            term = session.get(Termine, sel)
            c1, c2, c3 = st.columns(3)
            if c1.button("Toggle completato", key=f"{prefix}_term_compl_{inc.id}_{sel}"):
                term.completato = not term.completato
                session.commit()
                st.rerun()
            if c2.button("Toggle attivo", key=f"{prefix}_term_attivo_{inc.id}_{sel}"):
                term.attivo = not term.attivo
                session.commit()
                st.rerun()
            if c3.button("Elimina", type="secondary", key=f"{prefix}_term_del_{inc.id}_{sel}"):
                _safe_backup("prima_elimina_termine")
                session.delete(term)
                session.commit()
                st.rerun()
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
            t = Termine(
                incarico_id=inc.id,
                tipo_termine=tipo_t,
                giorni=int(giorni),
                decorrenza=decorrenza,
                data_manual=data_manual if decorrenza == "data_manual" else None,
                tipo_computo="naturali",
                attivo=attivo,
            )
            session.add(t)
            session.commit()
            st.success("Termine aggiunto.")
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
            session.commit()
            st.success("Date aggiornate.")
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
                        if t.tipo_termine == sc.tipo_termine and not t.completato
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
                    if col4.button(
                        "Marca completato",
                        key=f"{prefix}_calc_compl_{termine.id}",
                    ):
                        termine.completato = True
                        session.commit()
                        st.rerun()

    with tab_eventi:
        eventi_visibili = [e for e in inc.eventi if not getattr(e, "annullato", False)]
        if eventi_visibili:
            rows = []
            for e in eventi_visibili:
                rows.append({
                    "ID": e.id,
                    "Tipo": e.tipo,
                    "Data": fmt_date(e.data),
                    "Ora": e.ora or "-",
                    "Luogo": e.luogo or "-",
                    "Descrizione": (e.descrizione or "")[:100],
                    "Stato": stato_evento(e),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            with st.expander("Modifica / annulla evento"):
                ids = [e.id for e in eventi_visibili]
                sel = st.selectbox("Seleziona ID", ids, key=f"{prefix}_ev_action_{inc.id}")
                ev = session.get(Evento, sel)
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
            s = Sospensione(
                incarico_id=inc.id,
                data_inizio=di,
                data_fine=df or None,
                motivo=motivo or None,
                incide_su_scadenze=incide,
            )
            session.add(s)
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


# ------------------------- pagine -------------------------

def page_dashboard():
    st.title("Dashboard scadenziario")
    session = get_session()
    incarichi = session.query(Incarico).all()

    # Avviso e gestione dati demo
    n_demo = sum(1 for i in incarichi if i.origine_dato == "demo")
    if n_demo:
        st.warning(f"Sono presenti {n_demo} dati demo nel database.")
        with st.expander("Amministrazione dati demo"):
            confirm = st.checkbox("Confermo eliminazione dati demo", key="confirm_demo_del")
            if st.button("Elimina dati demo", disabled=not confirm, type="secondary"):
                _safe_backup("prima_elimina_demo")
                eliminati = elimina_dati_demo(session)
                st.success(f"Eliminati {eliminati} incarichi demo.")
                st.rerun()

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
    for inc in incarichi:
        prossima = trova_prossima_attivita_dashboard(inc, date.today())
        alert = classifica_per_dashboard(inc.stato, prossima)
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
        edit_url = f"./?page=Modifica%20incarico&incarico_id={inc.id}"

        rows.append({
            "id": inc.id,
            "Incarico": (
                f"<a href='{edit_url}' target='_self' "
                f"style='color:#1565c0;text-decoration:none;font-weight:600'>"
                f"{escape(incarico_label)}</a>"
                f"<br><a class='mobile-open-link' href='{edit_url}' target='_self'>Apri incarico</a>"
            ),
            "Ufficio": escape(inc.tribunale or ""),
            "Stato": escape(inc.stato or ""),
            "Priorita": escape(inc.priorita or "media"),
            "Prossima scadenza": fmt_date(prossima.data_scadenza) if prossima else "â€”",
            "Tipo termine": escape(prossima.tipo_termine if prossima else "da definire"),
            "Giorni residui": prossima.giorni_residui if prossima else None,
            "alert_raw": alert,
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
        rows = [r for r in rows if r["alert_raw"] in alert_filter]
    if stato_filter:
        rows = [r for r in rows if r["Stato"] in stato_filter]
    if prio_filter:
        rows = [r for r in rows if r["Priorita"] in prio_filter]
    if not show_waiting and "attesa_osservazioni" not in alert_filter:
        rows = [r for r in rows if r["alert_raw"] != "attesa_osservazioni"]
    if not show_closed:
        rows = [r for r in rows if r["alert_raw"] != "chiuso" and r["Stato"] != "chiuso"]

    rows.sort(key=lambda r: (ALERT_PRIORITY.get(r["alert_raw"], 99),
                             r["Giorni residui"] if r["Giorni residui"] is not None else 9999))

    counters = {}
    for r in rows:
        counters[r["alert_raw"]] = counters.get(r["alert_raw"], 0) + 1

    metric_rows = [metric_keys[:5], metric_keys[5:]]
    for metric_row in metric_rows:
        cols = st.columns(len(metric_row))
        for i, key in enumerate(metric_row):
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
        gg_disp = "â€”" if gg is None else str(gg)
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
        return

    st.subheader(f"{inc.tipo} {inc.numero_rg} â€” {inc.tribunale}")

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
                     if t.tipo_termine == sc.tipo_termine and not t.completato),
                    None,
                )
                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                col1.markdown(
                    f"**{sc.tipo_termine}** â€” {fmt_date(sc.data_scadenza)} "
                    f"({sc.giorni_residui:+d} gg)"
                )
                col2.markdown(alert_badge_html(sc.alert), unsafe_allow_html=True)
                col3.write("Completato" if sc.completato else "In corso")
                if not sc.completato and termine:
                    if col4.button("Marca completato", key=f"compl_{termine.id}"):
                        termine.completato = True
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
                    "Ora": e.ora or "â€”",
                    "Luogo": e.luogo or "â€”",
                    "Descrizione": (e.descrizione or "")[:80],
                    "Completato": "âœ”" if e.completato else "â€”",
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
        return

    st.subheader(f"{inc.tipo} {inc.numero_rg}")

    if inc.sospensioni:
        rows = []
        for s in inc.sospensioni:
            rows.append({
                "ID": s.id,
                "Inizio": fmt_date(s.data_inizio),
                "Fine": fmt_date(s.data_fine),
                "Incide": "âœ”" if s.incide_su_scadenze else "â€”",
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
            s = Sospensione(
                incarico_id=inc.id,
                data_inizio=di,
                data_fine=df or None,
                motivo=motivo or None,
                incide_su_scadenze=incide,
            )
            session.add(s)
            session.commit()
            st.success("Sospensione aggiunta.")
            st.rerun()

    session.close()


def page_verifica_import():
    st.title("Verifica import Excel")
    session = get_session()
    incs = (
        session.query(Incarico)
        .filter(Incarico.origine_dato == "import_excel")
        .order_by(Incarico.id)
        .all()
    )
    if not incs:
        st.info("Nessun incarico importato da Excel.")
        return

    da_correggere = [i for i in incs if is_numero_da_correggere(i.numero_rg)]
    if da_correggere:
        st.warning(
            f"{len(da_correggere)} incarichi con numero generico (es. IMPORT-*) "
            "richiedono correzione manuale."
        )

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

            # Eventi associati
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

    tab_dati, tab_termini, tab_eventi, tab_sospensioni, tab_documenti = st.tabs([
        "Dati",
        "Termini",
        "Eventi",
        "Sospensioni",
        "Documenti",
    ])
    with tab_dati:
        _render_incarico_editor(session, inc, "edit")
    with tab_termini:
        _render_termini_editor(session, inc, "edit_terms")
    with tab_eventi:
        _render_eventi_editor(session, inc, "edit_events")
    with tab_sospensioni:
        _render_sospensioni_editor(session, inc, "edit_sosp")
    with tab_documenti:
        _render_documenti_editor(session, inc, "edit_docs")
    session.close()


def page_import_excel():
    st.title("Import da Excel")
    st.caption(
        "Carica un file `.xlsx` con il layout dello scadenziario originario "
        "(A=descrizione, B=nomina, C=giuramento, D=inizio op., E=bozza, F=osservazioni, "
        "G=deposito, H=udienza, I=stato, K=note, L=sospensione, M=ripresa, N=gg sosp.). "
        "La colonna J (giorni alla scadenza) viene ignorata perchÃ© ricalcolata."
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
            - Se il numero procedura non Ã¨ riconoscibile nella descrizione, l'app assegna un codice provvisorio `IMPORT-n`.
            - Se l'ufficio o tribunale non Ã¨ ricavabile dalla descrizione, l'incarico viene importato con ufficio `(da definire)`.
            - Se il file ha piÃ¹ fogli, puoi indicare il nome del foglio qui sotto; se lasci vuoto, viene usato il primo.
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
        "Genera un file `.xlsx` con incarichi, termini, eventi, sospensioni e documenti "
        "presenti nel database locale."
    )
    st.metric("Incarichi esportabili", incarichi_count)

    data = genera_excel_export(session)
    st.download_button(
        "Scarica export Excel",
        data=data,
        file_name=f"scadenziario_ctu_export_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    session.close()


# ------------------------- router -------------------------

PAGES = {
    "Dashboard": page_dashboard,
    "Modifica incarico": page_modifica_incarico,
    "Nuovo incarico": page_nuovo_incarico,
    "Eventi": page_eventi,
    "Sospensioni": page_sospensioni,
    "Import Excel": page_import_excel,
    "Esporta Excel": page_export_excel,
    "Verifica import": page_verifica_import,
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
    if scelta != "Modifica incarico" and "incarico_id" in st.query_params:
        del st.query_params["incarico_id"]
    st.rerun()

PAGES[scelta]()


