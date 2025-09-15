# backend/performance.py

from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import desc
from .models import (
    Position,
    Instrument,
    Price,
    FxRate,
    PositionSnapshot,
    PortfolioSnapshot,
    Policy,
    PolicyTarget,
    Account,
)
from .schemas import (
    PortfolioOverview,
    SleeveWeight,
    PortfolioHistory,
    HistoryPoint,
    PositionDetail,
)

# Map any loose labels to your sleeve taxonomy
ASSET_NORMALIZE = {
    "Equity ETF": "Equity",
    "Stock": "Equity",
    "Equity": "Equity",
    "Bond": "Bonds",
    "Bonds": "Bonds",
    "Fund": "Fund",
    "Crypto": "Crypto",
    "Commodity": "Commodity",
    "Lending": "Lending",
    "Cash": "Cash",
    "Other": "Other",
}

def latest_px_eur(s: Session, inst_id: int, inst_ccy: str) -> float:
    """
    Get the most recent price for an instrument, converted to EUR using the latest FxRate for its currency.
    Returns 0.0 if no price is found.
    """
    # Get instrument for debugging
    from .models import Instrument
    inst = s.query(Instrument).filter(Instrument.id == inst_id).first()
    
    p = (
        s.query(Price)
        .filter(Price.instrument_id == inst_id)
        .order_by(desc(Price.ts))
        .first()
    )
    if not p:
        print(f"DEBUG: No price found for instrument {inst.code if inst else inst_id}")
        return 0.0
    
    # Debug crypto pricing specifically
    if inst and inst.asset_class == "Crypto":
        print(f"DEBUG: Portfolio calc using {inst.code}: €{p.price} from {p.ts}")

    # Special handling for crypto: prices are fetched in EUR regardless of instrument currency
    if inst and inst.asset_class == "Crypto":
        print(f"DEBUG: Crypto {inst.code}: returning EUR price directly €{p.price}")
        return float(p.price)
    
    # If already EUR, done
    if (inst_ccy or "").upper() == "EUR":
        return float(p.price)

    # Grab the latest FX for this ccy; if missing, return 0 so caller can use fallbacks
    fx = (
        s.query(FxRate)
        .filter(FxRate.ccy == (inst_ccy or "").upper())
        .order_by(desc(FxRate.ts))
        .first()
    )
    if not fx or not fx.rate_vs_eur:
        return 0.0

    # Price given in inst_ccy; convert to EUR
    rate = float(fx.rate_vs_eur)
    if rate <= 0:
        return 0.0
    return float(p.price) / rate


def _fallback_value(pos: Position) -> float:
    """
    When we don't have a live price (px_eur == 0), use sensible fallbacks:
      1) entry_total if present (> 0)
      2) quantity * cost_basis (per‑unit avg) if present
      3) else 0
    """
    entry_total = getattr(pos, "entry_total", 0.0) or 0.0
    if entry_total > 0:
        return float(entry_total)
    if pos.cost_basis and pos.cost_basis > 0 and pos.quantity and pos.quantity > 0:
        return float(pos.quantity) * float(pos.cost_basis)
    return 0.0


def latest_overview(s: Session, base_ccy: str = "EUR") -> PortfolioOverview:
    """
    Compute latest portfolio valuation:
      - value & weight by sleeve
      - freshness: 'ok' if we used a live price, 'stale' if we used fallbacks
      - drift vs policy targets (if saved)
    """
    sleeves_value = defaultdict(float)
    sleeves_fresh = defaultdict(lambda: "stale")
    total = 0.0

    rows = (
        s.query(Position, Instrument)
        .join(Instrument, Position.instrument_id == Instrument.id)
        .all()
    )

    for pos, inst in rows:
        sleeve = ASSET_NORMALIZE.get(inst.asset_class, inst.asset_class or "Other")
        px_eur = latest_px_eur(s, inst.id, inst.currency)
        if px_eur > 0:
            val = float(pos.quantity) * px_eur
            sleeves_fresh[sleeve] = "ok"
            # Debug crypto valuation specifically
            if inst.asset_class == "Crypto":
                print(f"DEBUG: Portfolio adding {inst.code}: {pos.quantity} × €{px_eur} = €{val}")
        else:
            val = _fallback_value(pos)
            # Debug missing crypto prices
            if inst.asset_class == "Crypto":
                print(f"DEBUG: Portfolio using fallback for {inst.code}: €{val} (no price found)")
            # keep 'stale' unless already 'ok' from another instrument in the same sleeve
        sleeves_value[sleeve] += val
        total += val

    by_sleeve = [
        SleeveWeight(
            asset_class=k,
            value=float(v),
            weight=(float(v) / float(total) if total > 0 else 0.0),
            freshness=sleeves_fresh[k],
        )
        for k, v in sleeves_value.items()
    ]

    # Drift vs policy
    drift = {}
    policy = s.query(Policy).first()
    targets = {}
    if policy:
        for t in s.query(PolicyTarget).filter(PolicyTarget.policy_id == policy.id).all():
            targets[t.asset_class] = t.weight

    for sw in by_sleeve:
        target = targets.get(sw.asset_class, sw.weight)
        drift[sw.asset_class] = sw.weight - (target or 0.0)

    return PortfolioOverview(total_value=float(total), by_sleeve=by_sleeve, drift=drift)


def capture_eod_snapshots(s: Session) -> None:
    """
    Take an end‑of‑day snapshot of each position and the portfolio aggregate,
    using the same pricing logic/fallbacks as latest_overview.
    """
    sleeves_value = defaultdict(float)
    total = 0.0

    rows = (
        s.query(Position, Instrument)
        .join(Instrument, Position.instrument_id == Instrument.id)
        .all()
    )
    for pos, inst in rows:
        px_eur = latest_px_eur(s, inst.id, inst.currency)
        val = (float(pos.quantity) * px_eur) if px_eur > 0 else _fallback_value(pos)

        s.add(
            PositionSnapshot(
                account_id=pos.account_id,
                instrument_id=inst.id,
                qty=float(pos.quantity),
                px_eur=float(px_eur),
                value_eur=float(val),
            )
        )
        sleeve = ASSET_NORMALIZE.get(inst.asset_class, inst.asset_class or "Other")
        sleeves_value[sleeve] += val
        total += val

    s.add(
        PortfolioSnapshot(
            total_value_eur=float(total),
            by_sleeve_json=dict((k, float(v)) for k, v in sleeves_value.items()),
        )
    )


def history(s: Session) -> PortfolioHistory:
    """
    Return time series of portfolio total value from snapshots.
    """
    points = []
    for snap in s.query(PortfolioSnapshot).order_by(PortfolioSnapshot.ts.asc()).all():
        points.append(
            HistoryPoint(ts=snap.ts.isoformat(), total_value_eur=float(snap.total_value_eur))
        )
    return PortfolioHistory(points=points)


def get_positions(s: Session) -> list[PositionDetail]:
    """
    Return detailed position data for the Holdings table.
    """
    rows = (
        s.query(Position, Instrument, Account)
        .join(Instrument, Position.instrument_id == Instrument.id)
        .join(Account, Position.account_id == Account.id)
        .all()
    )
    
    positions = []
    total_value = 0.0
    
    # First pass: calculate total value for weights
    for pos, inst, acc in rows:
        px_eur = latest_px_eur(s, inst.id, inst.currency)
        val = (float(pos.quantity) * px_eur) if px_eur > 0 else _fallback_value(pos)
        total_value += val
    
    # Second pass: build position details with weights
    for pos, inst, acc in rows:
        px_eur = latest_px_eur(s, inst.id, inst.currency)
        val = (float(pos.quantity) * px_eur) if px_eur > 0 else _fallback_value(pos)
        
        # Determine freshness - assume fresh if we got a live price
        freshness = "ok" if px_eur > 0 else "stale"
        
        # Handle special case for crypto currency display
        display_currency = inst.currency
        if inst.asset_class == "Crypto":
            display_currency = "EUR"  # Show EUR since crypto prices are in EUR
            
        positions.append(PositionDetail(
            name=inst.name or inst.code,
            code=inst.code,
            asset_class=ASSET_NORMALIZE.get(inst.asset_class, inst.asset_class or "Other"),
            account=acc.name,
            quantity=float(pos.quantity),
            price_eur=px_eur if px_eur > 0 else 0.0,
            value_eur=val,
            weight=val / total_value if total_value > 0 else 0.0,
            freshness=freshness,
            currency=display_currency
        ))
    
    # Sort by value descending
    positions.sort(key=lambda p: p.value_eur, reverse=True)
    return positions
