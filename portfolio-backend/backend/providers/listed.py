import os
import time
import requests
import random
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Cache to avoid repeated calls for the same symbol
_price_cache = {}
_cache_timeout = 300  # 5 minutes

# API configuration
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
IEX_CLOUD_TOKEN = os.getenv("IEX_CLOUD_TOKEN")

# Request timeout configuration
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 2

def _make_request_with_retry(url: str, headers: Dict[str, str] = None, params: Dict[str, str] = None) -> Optional[requests.Response]:
    """Make HTTP request with retry logic and proper timeout handling"""
    if headers is None:
        headers = {'User-Agent': 'Portfolio-Tracker/1.0'}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 200:
                return response
            elif response.status_code == 429:  # Rate limited
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt+1}/{MAX_RETRIES}")
                time.sleep(wait_time)
            else:
                logger.error(f"HTTP {response.status_code} for {url}")
                if attempt == MAX_RETRIES - 1:
                    return None
        except requests.exceptions.Timeout:
            logger.error(f"Timeout on attempt {attempt+1}/{MAX_RETRIES} for {url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error on attempt {attempt+1}/{MAX_RETRIES} for {url}: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    return None

def _fetch_alpha_vantage_price(symbol: str) -> Optional[float]:
    """Fetch price from Alpha Vantage API"""
    if not ALPHAVANTAGE_API_KEY:
        return None

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": symbol,
        "apikey": ALPHAVANTAGE_API_KEY
    }

    response = _make_request_with_retry(url, params=params)
    if not response:
        return None

    try:
        data = response.json()
        quote = data.get("Global Quote", {})
        price_str = quote.get("05. price")
        if price_str:
            return float(price_str)
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing Alpha Vantage response for {symbol}: {e}")

    return None

def _fetch_iex_cloud_price(symbol: str) -> Optional[float]:
    """Fetch price from IEX Cloud API"""
    if not IEX_CLOUD_TOKEN:
        return None

    url = f"https://cloud.iexapis.com/stable/stock/{symbol}/quote"
    params = {"token": IEX_CLOUD_TOKEN}

    response = _make_request_with_retry(url, params=params)
    if not response:
        return None

    try:
        data = response.json()
        price = data.get("latestPrice")
        if price is not None:
            return float(price)
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing IEX Cloud response for {symbol}: {e}")

    return None

# European exchange suffixes to try when base symbol fails
EUROPEAN_EXCHANGES = ['.MI', '.DE', '.AS', '.L', '.PA', '.SW']

def _fetch_yahoo_finance_single(symbol: str) -> Optional[tuple[float, str]]:
    """Fetch price from Yahoo Finance for a single symbol. Returns (price, currency) or None."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = _make_request_with_retry(url, headers=headers)
    if not response:
        return None

    try:
        data = response.json()
        result = data.get('chart', {}).get('result', [])
        if result:
            meta = result[0].get('meta', {})
            price = meta.get('regularMarketPrice')
            currency = meta.get('currency', 'USD')
            if price and price > 0:
                return (float(price), currency)
    except (ValueError, KeyError) as e:
        logger.error(f"Error parsing Yahoo Finance response for {symbol}: {e}")

    return None

def _fetch_yahoo_finance_price(symbol: str, expected_currency: str = None) -> Optional[float]:
    """
    Fetch price from Yahoo Finance API with automatic European exchange detection.
    If base symbol fails or returns wrong currency, tries European exchange suffixes.
    """
    # Try the base symbol first
    result = _fetch_yahoo_finance_single(symbol)
    if result:
        price, currency = result
        # If we got a price and either no expected currency or it matches, return it
        if expected_currency is None or currency == expected_currency:
            logger.info(f"Yahoo: {symbol} = {price} {currency}")
            return price
        logger.info(f"Yahoo: {symbol} returned {currency}, expected {expected_currency}. Trying European exchanges...")

    # If base symbol failed or returned wrong currency, try European exchanges
    base_symbol = symbol.split('.')[0] if '.' in symbol else symbol

    for suffix in EUROPEAN_EXCHANGES:
        test_symbol = f"{base_symbol}{suffix}"
        if test_symbol == symbol:
            continue  # already tried this exact symbol above
        result = _fetch_yahoo_finance_single(test_symbol)
        if result:
            price, currency = result
            # Prefer EUR for European exchanges
            if currency == 'EUR' or (expected_currency and currency == expected_currency):
                logger.info(f"Yahoo: Found {test_symbol} = {price} {currency}")
                return price

    return None

def fetch_price(code: str, asset_class: str, currency: str = None) -> Optional[float]:
    """
    Fetch stock/ETF prices using multiple providers with fallback
    Priority: Alpha Vantage -> IEX Cloud -> Yahoo Finance

    Args:
        code: Symbol/ticker code
        asset_class: Type of asset (stock, etf, equity, commodity)
        currency: Expected currency (EUR, USD, etc.) - helps find correct exchange
    """
    # Skip non-tradeable assets
    if asset_class.lower() not in ['stock', 'etf', 'equity', 'commodity']:
        logger.info(f"Skipping {code} - asset_class '{asset_class}' not supported for stock fetching")
        return None

    # Check cache first
    current_time = time.time()
    if code in _price_cache:
        cached_price, cached_time = _price_cache[code]
        if current_time - cached_time < _cache_timeout:
            logger.debug(f"Using cached price for {code}: {cached_price}")
            return cached_price

    # Try providers in priority order
    # For European securities (EUR currency), skip US-only providers and go straight to Yahoo
    if currency and currency.upper() == 'EUR':
        providers = [
            ("Yahoo Finance", lambda s: _fetch_yahoo_finance_price(s, expected_currency='EUR'))
        ]
    else:
        providers = [
            ("Alpha Vantage", _fetch_alpha_vantage_price),
            ("IEX Cloud", _fetch_iex_cloud_price),
            ("Yahoo Finance", lambda s: _fetch_yahoo_finance_price(s, expected_currency=currency))
        ]

    for provider_name, fetch_func in providers:
        try:
            price = fetch_func(code)
            if price and price > 0:
                _price_cache[code] = (float(price), current_time)
                logger.info(f"Fetched {code}: {price} from {provider_name}")
                return float(price)
        except Exception as e:
            logger.error(f"Error fetching {code} from {provider_name}: {e}")
            continue

    logger.warning(f"No price found for {code} from any provider")
    return None

def fetch_bulk_prices(symbols: List[str]) -> Dict[str, float]:
    """
    Fetch multiple stock prices with intelligent batching and rate limiting
    """
    if not symbols:
        return {}

    logger.info(f"Fetching prices for {len(symbols)} symbols")

    prices = {}
    current_time = time.time()

    # Filter out cached symbols
    symbols_to_fetch = []
    for symbol in symbols:
        if symbol in _price_cache:
            cached_price, cached_time = _price_cache[symbol]
            if current_time - cached_time < _cache_timeout:
                prices[symbol] = cached_price
                logger.debug(f"Using cached price for {symbol}")
                continue
        symbols_to_fetch.append(symbol)

    if not symbols_to_fetch:
        logger.info("All prices were cached")
        return prices

    logger.info(f"Need to fetch {len(symbols_to_fetch)} symbols from APIs")

    # Fetch individual prices with rate limiting
    for i, symbol in enumerate(symbols_to_fetch):
        try:
            logger.debug(f"Fetching {symbol} ({i+1}/{len(symbols_to_fetch)})")

            # Add delay between requests to respect rate limits
            if i > 0:
                delay = random.uniform(0.8, 1.5)
                time.sleep(delay)

            price = fetch_price(symbol, "equity")
            if price:
                prices[symbol] = price

        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            continue

    logger.info(f"Successfully fetched {len([p for p in prices.values() if p])} out of {len(symbols)} prices")
    return prices
