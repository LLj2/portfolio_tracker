import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base, Instrument, Account, Position, Price, FxRate, Policy, PolicyTarget
from . import schemas

# Use DATABASE_URL if provided, otherwise construct from individual parts
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DB_URL = DATABASE_URL
else:
    DB_URL = "postgresql+psycopg2://{u}:{p}@{h}:{port}/{d}".format(
        u=os.getenv("POSTGRES_USER","postgres"),
        p=os.getenv("POSTGRES_PASSWORD","postgres"),
        h=os.getenv("POSTGRES_HOST","localhost"),
        port=os.getenv("POSTGRES_PORT","5432"),
        d=os.getenv("POSTGRES_DB","portfolio"),
    )

engine = create_engine(DB_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db():
    Base.metadata.create_all(engine)

def upsert_instrument(s, code, name, asset_class, currency):
    inst = s.query(Instrument).filter(Instrument.code==code).one_or_none()
    if not inst:
        inst = Instrument(code=code, name=name, asset_class=asset_class, currency=currency)
        s.add(inst); s.flush()
    else:
        inst.name = name or inst.name
        inst.asset_class = asset_class or inst.asset_class
        inst.currency = currency or inst.currency
    return inst

def upsert_position(s, account_id, instrument_id, quantity, cost_basis, entry_total):
    pos = s.query(Position).filter(
        Position.account_id==account_id, Position.instrument_id==instrument_id
    ).one_or_none()
    if not pos:
        pos = Position(
            account_id=account_id,
            instrument_id=instrument_id,
            quantity=quantity,
            cost_basis=cost_basis,
            entry_total=entry_total,
        )
        s.add(pos); s.flush()
    else:
        pos.quantity = quantity
        pos.cost_basis = cost_basis
        pos.entry_total = entry_total
    return pos


def create_account(s, acc: schemas.AccountCreate):
    obj = Account(name=acc.name, institution=acc.institution, currency=acc.currency)
    s.add(obj); s.commit(); s.refresh(obj)
    return schemas.AccountOut.model_validate(obj, from_attributes=True)

def set_policy(s, policy: schemas.PolicyIn):
    s.query(PolicyTarget).delete()
    s.query(Policy).delete()
    p = Policy(base_currency=policy.base_currency)
    s.add(p); s.flush()
    for t in policy.targets:
        s.add(PolicyTarget(policy_id=p.id, asset_class=t.asset_class, weight=t.weight, band=t.band))
    return p

def get_policy(s):
    policy = s.query(Policy).first()
    if not policy:
        return None
    
    targets = s.query(PolicyTarget).filter(PolicyTarget.policy_id == policy.id).all()
    target_schemas = [
        schemas.PolicyTargetIn(
            asset_class=t.asset_class,
            weight=t.weight,
            band=t.band
        ) for t in targets
    ]
    
    return schemas.PolicyIn(
        base_currency=policy.base_currency,
        targets=target_schemas
    )
