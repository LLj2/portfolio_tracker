import os
import requests
import time
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# Request configuration
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 2

SYMBOL_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum", 
    "SOL": "solana",
    "LINK": "chainlink",
    "ADA": "cardano",
    "AAVE": "aave",
    "INJ": "injective-protocol",
    "FIL": "filecoin",
    "NEXO": "nexo",
    "SUI": "sui",
    "PYTH": "pyth-network",
    "APTOS": "aptos",
    "ENA": "ethena",
    "AI16Z": "ai16z",
    "EURX": "eurx",  # Digital euro - fixed at ~1 EUR
}

def _make_request_with_retry(url: str, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    """Make HTTP request with retry logic for CoinGecko API"""
    headers = {'User-Agent': 'Portfolio-Tracker/1.0'}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:  # Rate limited
                wait_time = RETRY_DELAY * (2 ** attempt)
                logger.warning(f"CoinGecko rate limited, waiting {wait_time}s before retry {attempt+1}/{MAX_RETRIES}")
                time.sleep(wait_time)
            else:
                response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout on attempt {attempt+1}/{MAX_RETRIES} for {url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error on attempt {attempt+1}/{MAX_RETRIES} for {url}: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    raise requests.exceptions.RequestException(f"Failed to fetch {url} after {MAX_RETRIES} attempts")

def fetch_price(code: str) -> float:
    """Fetch crypto price from CoinGecko with robust error handling"""
    sym = code.split(":")[-1].upper()

    # Special handling for EURX (digital euro) - pegged to EUR
    if sym == "EURX":
        logger.debug(f"Using fixed price for {sym}: 1.0 EUR")
        return 1.0

    coin_id = SYMBOL_TO_ID.get(sym)
    if not coin_id:
        logger.error(f"Unsupported crypto symbol: {sym}")
        raise ValueError(f"Unsupported crypto symbol: {sym}")

    base = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
    url = f"{base}/simple/price?ids={coin_id}&vs_currencies=eur"

    # Add delay to avoid rate limiting (CoinGecko free tier)
    time.sleep(1.0)

    try:
        response = _make_request_with_retry(url)
        data = response.json()
        price = float(data[coin_id]["eur"])
        logger.info(f"Fetched {sym}: {price} EUR from CoinGecko")
        return price
    except (KeyError, ValueError) as e:
        logger.error(f"Error parsing CoinGecko response for {sym}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fetching price for {sym}: {e}")
        raise

def fetch_bulk_prices(codes: List[str]) -> Dict[str, float]:
    """Fetch prices for multiple cryptos with robust error handling"""
    logger.info(f"Fetching bulk crypto prices for {len(codes)} symbols")

    # Handle EURX separately
    prices = {}
    crypto_codes = []

    for code in codes:
        sym = code.split(":")[-1].upper() if ":" in code else code.upper()
        if sym == "EURX":
            prices[code] = 1.0
            logger.debug(f"Using fixed price for {code}: 1.0 EUR")
        elif sym in SYMBOL_TO_ID:
            crypto_codes.append(code)
        else:
            logger.warning(f"Unsupported crypto symbol: {sym}")

    if not crypto_codes:
        return prices

    # Build list of CoinGecko IDs
    coin_ids = []
    code_to_id = {}

    for code in crypto_codes:
        sym = code.split(":")[-1].upper() if ":" in code else code.upper()
        if sym in SYMBOL_TO_ID:
            coin_id = SYMBOL_TO_ID[sym]
            coin_ids.append(coin_id)
            code_to_id[coin_id] = code

    if not coin_ids:
        return prices

    # Make bulk API call
    base = os.getenv("COINGECKO_BASE", "https://api.coingecko.com/api/v3")
    ids_param = ",".join(coin_ids)
    url = f"{base}/simple/price?ids={ids_param}&vs_currencies=eur"

    try:
        response = _make_request_with_retry(url, timeout=30)
        data = response.json()

        # Map results back to original codes
        for coin_id, price_data in data.items():
            if coin_id in code_to_id and "eur" in price_data:
                original_code = code_to_id[coin_id]
                price = float(price_data["eur"])
                prices[original_code] = price
                logger.info(f"Fetched {original_code}: {price} EUR")

        logger.info(f"Successfully fetched {len(prices)} crypto prices")
        return prices

    except Exception as e:
        logger.error(f"Error in bulk crypto price fetch: {e}")
        # Fallback to individual calls
        logger.info("Falling back to individual crypto price calls")
        for code in crypto_codes:
            try:
                price = fetch_price(code)
                if price:
                    prices[code] = price
            except Exception as individual_error:
                logger.error(f"Individual crypto price fetch failed for {code}: {individual_error}")
                continue

        return prices
