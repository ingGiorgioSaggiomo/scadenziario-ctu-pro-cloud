from datetime import date, datetime
from typing import Optional

from decimal import Decimal

from sqlalchemy import String, Text, Date, DateTime, Integer, ForeignKey, Boolean, Numeric, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Incarico(Base):
    __tablename__ = "incarichi"

    id: Mapped[int] = mapped_column(primary_key=True)
    numero_rg: Mapped[str] = mapped_column(String(50))
    tribunale: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[str] = mapped_column(String(50))  # CTU, Procura, RESA, Ordine a fare, Incarico tecnico
    giudice: Mapped[Optional[str]] = mapped_column(String(200))
    parti: Mapped[Optional[str]] = mapped_column(Text)
    oggetto: Mapped[Optional[str]] = mapped_column(Text)
    data_conferimento: Mapped[date] = mapped_column(Date)
    data_giuramento: Mapped[Optional[date]] = mapped_column(Date)
    data_inizio_operazioni: Mapped[Optional[date]] = mapped_column(Date)
    data_invio_bozza: Mapped[Optional[date]] = mapped_column(Date)
    data_ricezione_osservazioni: Mapped[Optional[date]] = mapped_column(Date)
    stato: Mapped[str] = mapped_column(String(30), default="attivo")  # attivo, sospeso, chiuso
    priorita: Mapped[str] = mapped_column(String(20), default="media")  # alta, media, bassa
    origine_dato: Mapped[str] = mapped_column(String(20), default="manuale")  # demo, import_excel, manuale
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    termini: Mapped[list["Termine"]] = relationship(back_populates="incarico", cascade="all, delete-orphan")
    eventi: Mapped[list["Evento"]] = relationship(back_populates="incarico", cascade="all, delete-orphan")
    sospensioni: Mapped[list["Sospensione"]] = relationship(back_populates="incarico", cascade="all, delete-orphan")
    documenti: Mapped[list["Documento"]] = relationship(back_populates="incarico", cascade="all, delete-orphan")
    pagamenti: Mapped[list["Pagamento"]] = relationship(back_populates="incarico", cascade="all, delete-orphan")
    modifiche_chat: Mapped[list["ModificaChat"]] = relationship(back_populates="incarico", passive_deletes=True)
    storico_termini: Mapped[list["StoricoTermine"]] = relationship(
        back_populates="incarico",
        cascade="all, delete-orphan",
    )


class Termine(Base):
    __tablename__ = "termini"

    id: Mapped[int] = mapped_column(primary_key=True)
    incarico_id: Mapped[int] = mapped_column(ForeignKey("incarichi.id"), index=True)
    tipo_termine: Mapped[str] = mapped_column(String(80))  # bozza, osservazioni, deposito, udienza, personalizzato
    giorni: Mapped[int] = mapped_column(Integer)
    decorrenza: Mapped[str] = mapped_column(String(80))  # data_nomina, data_giuramento, data_inizio_operazioni, data_invio_bozza, data_scadenza_osservazioni, data_ricezione_osservazioni, data_manual
    data_manual: Mapped[Optional[date]] = mapped_column(Date)
    tipo_computo: Mapped[str] = mapped_column(String(20), default="naturali")  # naturali, lavorativi
    data_scadenza: Mapped[Optional[date]] = mapped_column(Date)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    completato: Mapped[bool] = mapped_column(Boolean, default=False)
    prorogato: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text)

    incarico: Mapped["Incarico"] = relationship(back_populates="termini")
    evento_collegato: Mapped[Optional["Evento"]] = relationship(
        back_populates="termine",
        uselist=False,
        foreign_keys="Evento.termine_id",
    )
    storico: Mapped[list["StoricoTermine"]] = relationship(
        back_populates="termine",
        passive_deletes=True,
    )


class Evento(Base):
    __tablename__ = "eventi"
    __table_args__ = (Index("ix_eventi_termine_id", "termine_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    incarico_id: Mapped[int] = mapped_column(ForeignKey("incarichi.id"), index=True)
    termine_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("termini.id", ondelete="SET NULL"),
        nullable=True,
    )
    tipo: Mapped[str] = mapped_column(String(80))  # udienza, sopralluogo, riunione, deposito, nota
    data: Mapped[Optional[date]] = mapped_column(Date)
    ora: Mapped[Optional[str]] = mapped_column(String(10))
    luogo: Mapped[Optional[str]] = mapped_column(String(300))
    descrizione: Mapped[Optional[str]] = mapped_column(Text)
    completato: Mapped[bool] = mapped_column(Boolean, default=False)
    annullato: Mapped[bool] = mapped_column(Boolean, default=False)

    incarico: Mapped["Incarico"] = relationship(back_populates="eventi")
    termine: Mapped[Optional["Termine"]] = relationship(
        back_populates="evento_collegato",
        foreign_keys=[termine_id],
    )


class StoricoTermine(Base):
    __tablename__ = "storico_termini"
    __table_args__ = (
        Index("ix_storico_termini_incarico_id", "incarico_id"),
        Index("ix_storico_termini_termine_id", "termine_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    incarico_id: Mapped[int] = mapped_column(ForeignKey("incarichi.id", ondelete="CASCADE"))
    termine_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("termini.id", ondelete="SET NULL"),
        nullable=True,
    )
    modificato_il: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    azione: Mapped[str] = mapped_column(String(40))
    motivo: Mapped[Optional[str]] = mapped_column(Text)
    tipo_termine: Mapped[str] = mapped_column(String(80))
    giorni: Mapped[int] = mapped_column(Integer)
    decorrenza: Mapped[str] = mapped_column(String(80))
    data_manual: Mapped[Optional[date]] = mapped_column(Date)
    data_scadenza: Mapped[Optional[date]] = mapped_column(Date)
    attivo: Mapped[bool] = mapped_column(Boolean)
    completato: Mapped[bool] = mapped_column(Boolean)
    prorogato: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[Optional[str]] = mapped_column(Text)

    incarico: Mapped["Incarico"] = relationship(back_populates="storico_termini")
    termine: Mapped[Optional["Termine"]] = relationship(back_populates="storico")


class Sospensione(Base):
    __tablename__ = "sospensioni"

    id: Mapped[int] = mapped_column(primary_key=True)
    incarico_id: Mapped[int] = mapped_column(ForeignKey("incarichi.id"), index=True)
    data_inizio: Mapped[date] = mapped_column(Date)
    data_fine: Mapped[Optional[date]] = mapped_column(Date)
    motivo: Mapped[Optional[str]] = mapped_column(Text)
    incide_su_scadenze: Mapped[bool] = mapped_column(Boolean, default=True)

    incarico: Mapped["Incarico"] = relationship(back_populates="sospensioni")


class Documento(Base):
    __tablename__ = "documenti"

    id: Mapped[int] = mapped_column(primary_key=True)
    incarico_id: Mapped[int] = mapped_column(ForeignKey("incarichi.id"), index=True)
    nome: Mapped[str] = mapped_column(String(300))
    percorso: Mapped[Optional[str]] = mapped_column(String(500))
    tipo: Mapped[Optional[str]] = mapped_column(String(80))  # perizia, verbale, allegato, corrispondenza
    data_documento: Mapped[Optional[date]] = mapped_column(Date)
    note: Mapped[Optional[str]] = mapped_column(Text)

    incarico: Mapped["Incarico"] = relationship(back_populates="documenti")


class Pagamento(Base):
    __tablename__ = "pagamenti"

    id: Mapped[int] = mapped_column(primary_key=True)
    incarico_id: Mapped[int] = mapped_column(ForeignKey("incarichi.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(30), default="acconto")  # acconto, saldo, altro
    descrizione: Mapped[Optional[str]] = mapped_column(String(200))
    imponibile: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    spese: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    importo_dovuto: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    importo_ricevuto: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    data_riferimento: Mapped[Optional[date]] = mapped_column(Date)
    data_pagamento: Mapped[Optional[date]] = mapped_column(Date)
    pagatore: Mapped[Optional[str]] = mapped_column(String(200))
    note: Mapped[Optional[str]] = mapped_column(Text)

    incarico: Mapped["Incarico"] = relationship(back_populates="pagamenti")


class ModificaChat(Base):
    __tablename__ = "modifiche_chat"

    id: Mapped[int] = mapped_column(primary_key=True)
    incarico_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("incarichi.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    azione: Mapped[str] = mapped_column(String(80))
    richiesta: Mapped[Optional[str]] = mapped_column(Text)
    prima: Mapped[Optional[str]] = mapped_column(Text)
    dopo: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)

    incarico: Mapped[Optional["Incarico"]] = relationship(back_populates="modifiche_chat")
