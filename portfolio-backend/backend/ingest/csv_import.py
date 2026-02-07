import csv
from io import StringIO
from typing import Dict, Set, Tuple
from .. import db
from ..models import Account, Position

CLASS_MAP = {
    "stock": "Equity",
    "equity": "Equity",
    "bond": "Bonds",
    "bonds": "Bonds",
    "fund": "Fund",
    "crypto": "Crypto",
    "commodity": "Commodity",
    "lending": "Lending",
    "cash": "Cash",
    "other": "Other",
}

def _parse_float(v, default=0.0):
    if v is None: return default
    v = str(v).strip()
    if v == "" or v.lower() == "na": return default
    try:
        # Remove currency symbols, commas, and extra spaces
        import re
        # Remove currency symbols (€, $, £, etc.), commas, and extra spaces
        v = re.sub(r'[€$£¥₹₽\s,]', '', v)
        # Replace common decimal separators
        v = v.replace(',', '.')
        return float(v)
    except:
        return default

def _norm_class(x: str) -> str:
    if not x: return "Other"
    return CLASS_MAP.get(x.strip().lower(), x.strip())

def _get_or_create_account(session, name: str, currency_hint: str = "EUR"):
    acc = session.query(Account).filter(Account.name == name).one_or_none()
    if not acc:
        acc = Account(name=name, institution="custom", currency=currency_hint or "EUR")
        session.add(acc); session.flush()
    return acc

def import_holdings_csv(session, csv_text: str) -> int:
    """
    REPLACE MODE per account:
      • Upsert rows present in CSV (qty>0)
      • Delete any positions for that account not in CSV
      • qty==0 in CSV → delete/close
    Supports:
      • book_cost = per-unit avg price (optional)
      • initial   = total entry amount (optional)
      • if one is missing and qty>0, derive the other
      • auto-code CASH rows as CASH:<CURRENCY> if code missing
      • normalize asset_class (e.g., 'Stock' → 'Equity')
    """
    f = StringIO(csv_text)
    reader = csv.DictReader(f)
    rows_by_account: Dict[str, list] = {}
    for row in reader:
        acct = (row.get("account") or "").strip()
        rows_by_account.setdefault(acct, []).append(row)

    total_rows = 0

    for account_name, rows in rows_by_account.items():
        sample_ccy = (rows[0].get("currency") or "EUR").strip()
        acc = _get_or_create_account(session, account_name, currency_hint=sample_ccy)

        csv_codes: Set[str] = set()
        upserts: Dict[str, Tuple[float, float, float, str, str, str, str]] = {}
        # code -> (qty, avg_price, entry_total, name, asset_class, currency, instrument_type)

        for row in rows:
            name = (row.get("name") or "").strip()
            currency = (row.get("currency") or "EUR").strip()
            asset_class = _norm_class(row.get("asset_class") or "")
            code = (row.get("isin_or_symbol") or "").strip()
            instrument_type = (row.get("instrument_type") or "Other").strip()

            # Auto-code CASH if missing code
            if (not code) and asset_class == "Cash":
                code = f"CASH:{currency.upper()}"

            qty = _parse_float(row.get("quantity"))
            avg_price = _parse_float(row.get("book_cost"))   # per-unit
            entry_total = _parse_float(row.get("initial"))   # total
            
            # Debug logging for crypto positions
            if asset_class == "Crypto":
                print(f"DEBUG: Processing crypto {code}: qty={qty}, asset_class={asset_class}, currency={currency}")

            # derive missing piece if possible
            if qty > 0:
                if avg_price <= 0 and entry_total > 0:
                    avg_price = entry_total / qty
                if entry_total <= 0 and avg_price > 0:
                    entry_total = avg_price * qty

            # track code presence
            if code:
                csv_codes.add(code)

            # qty==0 → treated as close (handled in deletion pass), so don't upsert
            if qty <= 0 or not code:
                if asset_class == "Crypto":
                    print(f"DEBUG: SKIPPING crypto {code}: qty={qty}, code_empty={not code}")
                continue

            upserts[code] = (qty, avg_price, entry_total, name, asset_class, currency, instrument_type)

        # Upsert positions
        for code, (qty, avg, total, name, asset_class, currency, instrument_type) in upserts.items():
            inst = db.upsert_instrument(
                session,
                code=code,
                name=name,
                asset_class=asset_class,
                currency=currency,
                instrument_type=instrument_type,
            )
            db.upsert_position(
                session,
                account_id=acc.id,
                instrument_id=inst.id,
                quantity=qty,
                cost_basis=avg,        # per-unit
                entry_total=total,     # total
            )
            total_rows += 1

        # Delete positions not present in CSV for this account or explicitly qty==0
        existing = session.query(Position).filter(Position.account_id == acc.id).all()
        for pos in existing:
            from ..models import Instrument
            inst = session.query(Instrument).filter(Instrument.id == pos.instrument_id).first()
            if not inst:
                continue
            inst_code = inst.code
            if inst_code not in csv_codes:
                session.delete(pos)
            elif inst_code in csv_codes and inst_code not in upserts:
                # present in CSV but qty==0
                session.delete(pos)

    return total_rows

def import_nav_csv(session, csv_text: str) -> int:
    """
    Append NAV prices (per-unit) for funds/lending/etc.
    CSV columns: date,isin_or_symbol,nav,currency[, name, initial]
    If 'initial' is provided and a position exists, we DO NOT overwrite it here
    (initial is managed via holdings upload); NAV is just the latest price.
    """
    f = StringIO(csv_text)
    reader = csv.DictReader(f)
    cnt = 0
    for row in reader:
        code = (row.get("isin_or_symbol") or "").strip()
        currency = (row.get("currency") or "EUR").strip()
        name = (row.get("name") or "").strip()
        total_value = _parse_float(row.get("nav"))
        
        # If no ISIN code, use name as code (prefixed with FUND:)
        if not code and name:
            code = f"FUND:{name.replace(' ', '_')}"
        
        if not code or total_value <= 0:
            continue
            
        # Find the position to get the quantity and calculate per-unit price
        inst = db.upsert_instrument(session, code=code, name=name, asset_class="Bonds", currency=currency)
        
        # Look for existing position to get quantity
        from ..models import Position, Instrument
        
        # Try exact code match first
        position = session.query(Position).join(Instrument).filter(
            Instrument.code == code
        ).first()
        
        # If no match and we have a name, try matching by name for empty ISIN cases
        if not position and name:
            position = session.query(Position).join(Instrument).filter(
                Instrument.name == name
            ).first()
        
        if position and position.quantity > 0:
            # Calculate per-unit price: total_value / quantity
            per_unit_price = total_value / position.quantity
            print(f"MATCHED: {code} | {name} | qty: {position.quantity} | total: {total_value} | per_unit: {per_unit_price}")
        else:
            # No position found, use total value as per-unit price (fallback)
            per_unit_price = total_value
            print(f"NO MATCH: {code} | {name} | total: {total_value} | using as per_unit price")
            
        from ..models import Price
        session.add(Price(instrument_id=inst.id, price=per_unit_price))
        cnt += 1
    return cnt
