from sqlalchemy.orm import Session
from ..models import Instrument, Price, FxRate
from . import crypto, fx_ecb, listed

def run_price_cycle(s: Session):
    # FX first
    try:
        fx = fx_ecb.fetch_ecb_rates()
        for ccy, rate in fx.items():
            s.add(FxRate(ccy=ccy, rate_vs_eur=rate))
    except Exception as e:
        print("FX fetch error:", e)

    instruments = s.query(Instrument).all()
    
    # Collect all crypto symbols for bulk fetch
    crypto_instruments = []
    other_instruments = []
    
    print(f"DEBUG: Total instruments found: {len(instruments)}")
    for inst in instruments:
        print(f"DEBUG: Instrument {inst.code} | asset_class: '{inst.asset_class}'")
        if inst.asset_class.lower() == "crypto":
            crypto_instruments.append(inst)
        else:
            other_instruments.append(inst)
    
    print(f"DEBUG: Found {len(crypto_instruments)} crypto instruments")
    print(f"DEBUG: Crypto symbols: {[inst.code for inst in crypto_instruments]}")
    
    # Bulk fetch crypto prices
    if crypto_instruments:
        print(f"DEBUG: Starting crypto price fetch for {len(crypto_instruments)} cryptos...")
        try:
            print("DEBUG: Calling crypto.fetch_bulk_prices...")
            crypto_prices = crypto.fetch_bulk_prices([inst.code for inst in crypto_instruments])
            print(f"DEBUG: Got crypto prices: {len(crypto_prices)} results")
            for inst in crypto_instruments:
                if inst.code in crypto_prices:
                    s.add(Price(instrument_id=inst.id, price=float(crypto_prices[inst.code])))
                    print(f"DEBUG: Added crypto price for {inst.code}: €{crypto_prices[inst.code]} (fetched in EUR)")
            s.flush()  # Ensure crypto prices are written to DB immediately
        except Exception as e:
            print(f"Bulk crypto fetch error: {e}")
            print(f"DEBUG: Exception type: {type(e)}")
            # Fallback to individual calls with longer delay
            for inst in crypto_instruments:
                try:
                    px = crypto.fetch_price(inst.code)
                    if px is not None:
                        s.add(Price(instrument_id=inst.id, price=float(px)))
                except Exception as e:
                    print(f"Price fetch error for {inst.code}: {e}")
    else:
        print("DEBUG: No crypto instruments found for pricing")
    
    # Handle non-crypto instruments with bulk fetching for stocks
    stock_instruments = []
    commodity_instruments = []
    cash_instruments = []
    
    for inst in other_instruments:
        print(f"Processing instrument: {inst.code} | asset_class: '{inst.asset_class}'")
        if inst.asset_class.lower() in ['stock', 'etf', 'equity']:
            stock_instruments.append(inst)
        elif inst.asset_class.lower() == 'cash':
            cash_instruments.append(inst)
        else:
            commodity_instruments.append(inst)
    
    # Bulk fetch stock prices
    if stock_instruments:
        print(f"Starting stock price fetch for {len(stock_instruments)} stocks...")
        print(f"Symbols: {[inst.code for inst in stock_instruments]}")
        try:
            stock_prices = listed.fetch_bulk_prices([inst.code for inst in stock_instruments])
            print(f"Bulk fetch returned {len(stock_prices)} prices: {list(stock_prices.keys())}")
            for inst in stock_instruments:
                if inst.code in stock_prices:
                    s.add(Price(instrument_id=inst.id, price=float(stock_prices[inst.code])))
                    print(f"Added price for {inst.code}: {stock_prices[inst.code]}")
                else:
                    print(f"No price returned for {inst.code}")
        except Exception as e:
            print(f"Bulk stock fetch error: {e}")
            # Fallback to individual calls
            for inst in stock_instruments:
                try:
                    px = listed.fetch_price(inst.code, inst.asset_class)
                    if px is not None:
                        s.add(Price(instrument_id=inst.id, price=float(px)))
                except Exception as e:
                    print(f"Stock price fetch error for {inst.code}: {e}")
    
    # Handle cash instruments (always price = 1.0)
    for inst in cash_instruments:
        try:
            print(f"Setting cash price for {inst.code}: 1.0")
            s.add(Price(instrument_id=inst.id, price=1.0))
        except Exception as e:
            print(f"Cash price error for {inst.code}: {e}")
    
    # Handle commodities and bonds - use bulk fetching like stocks
    if commodity_instruments:
        print(f"Starting commodity/bond price fetch for {len(commodity_instruments)} instruments...")
        
        # Separate actual commodities from bonds
        actual_commodities = []
        bonds = []
        
        for inst in commodity_instruments:
            if inst.asset_class.lower() == 'commodity':
                actual_commodities.append(inst)
            else:
                bonds.append(inst)
        
        # Fetch commodity ETCs (like gold) using bulk method
        if actual_commodities:
            try:
                commodity_prices = listed.fetch_bulk_prices([inst.code for inst in actual_commodities])
                for inst in actual_commodities:
                    if inst.code in commodity_prices:
                        s.add(Price(instrument_id=inst.id, price=float(commodity_prices[inst.code])))
                        print(f"✅ Commodity {inst.code}: {commodity_prices[inst.code]}")
                    else:
                        print(f"❌ No price for commodity {inst.code}")
            except Exception as e:
                print(f"Bulk commodity fetch error: {e}")
        
        # For bonds, skip pricing for now (they need special handling)
        for inst in bonds:
            print(f"⏭️  Skipping bond pricing for {inst.code} (needs bond data provider)")
            # TODO: Implement bond pricing with dedicated provider
