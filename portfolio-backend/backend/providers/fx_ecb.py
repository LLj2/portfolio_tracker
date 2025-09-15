import os
import requests
import xml.etree.ElementTree as ET
import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)

# Request configuration
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
RETRY_DELAY = 2

def _make_request_with_retry(url: str) -> requests.Response:
    """Make HTTP request with retry logic for ECB API"""
    headers = {'User-Agent': 'Portfolio-Tracker/1.0'}

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response
            else:
                response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout on attempt {attempt+1}/{MAX_RETRIES} for ECB API")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error on attempt {attempt+1}/{MAX_RETRIES} for ECB API: {e}")

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)

    raise requests.exceptions.RequestException(f"Failed to fetch ECB rates after {MAX_RETRIES} attempts")

def fetch_ecb_rates() -> Dict[str, float]:
    """Fetch EUR exchange rates from ECB with robust error handling"""
    url = os.getenv("ECB_FX_BASE", "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml")

    try:
        logger.info("Fetching ECB FX rates")
        response = _make_request_with_retry(url)

        # Parse XML
        root = ET.fromstring(response.content)
        ns = {
            "gesmes": "http://www.gesmes.org/xml/2002-08-01",
            "def": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
        }

        rates = {"EUR": 1.0}

        for cube in root.findall(".//def:Cube/def:Cube/def:Cube", ns):
            ccy = cube.attrib.get("currency")
            rate = cube.attrib.get("rate")
            if ccy and rate:
                try:
                    rates[ccy] = float(rate)
                except ValueError:
                    logger.warning(f"Invalid rate for currency {ccy}: {rate}")
                    continue

        logger.info(f"Successfully fetched {len(rates)} ECB exchange rates")
        return rates

    except ET.ParseError as e:
        logger.error(f"Error parsing ECB XML response: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fetching ECB rates: {e}")
        raise
