from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, ForeignKey, DateTime, JSON
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)  # ISIN or symbol (CRYPTO:BTC, LEND:ID)
    name: Mapped[str] = mapped_column(String)
    asset_class: Mapped[str] = mapped_column(String)        # Equity, Bonds, Fund, Crypto, Commodity, Lending, Cash, Other
    instrument_type: Mapped[str] = mapped_column(String, default="Other", nullable=True)  # Stock, ETF, ETC, Fund, Crypto, P2P, Cash
    currency: Mapped[str] = mapped_column(String, default="EUR")

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    institution: Mapped[str] = mapped_column(String)
    currency: Mapped[str] = mapped_column(String, default="EUR")

class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    cost_basis: Mapped[float] = mapped_column(Float, default=0.0)  # per-unit avg price (if known)
    entry_total: Mapped[float] = mapped_column(Float, default=0.0) # total entry amount (if known)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

class Price(Base):
    __tablename__ = "prices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    price: Mapped[float] = mapped_column(Float)  # instrument currency

class FxRate(Base):
    __tablename__ = "fx_rates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ccy: Mapped[str] = mapped_column(String)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    rate_vs_eur: Mapped[float] = mapped_column(Float)

class Policy(Base):
    __tablename__ = "policy"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base_currency: Mapped[str] = mapped_column(String, default="EUR")

class PolicyTarget(Base):
    __tablename__ = "policy_targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policy.id"))
    asset_class: Mapped[str] = mapped_column(String)
    weight: Mapped[float] = mapped_column(Float)
    band: Mapped[float] = mapped_column(Float)


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer)
    instrument_id: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    qty: Mapped[float] = mapped_column(Float)
    px_eur: Mapped[float] = mapped_column(Float)
    value_eur: Mapped[float] = mapped_column(Float)

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    total_value_eur: Mapped[float] = mapped_column(Float)
    by_sleeve_json: Mapped[dict] = mapped_column(JSON)
