"""MCP tools supplying bank listings and exchange rates."""

import json
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("bank-lookup")

USER_AGENT = "BankStatementVerification/1.0"
REQUEST_TIMEOUT = 15


def _fetch_json(url):
    """Fetch a URL with the application's user agent and return its decoded JSON."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.load(response)


def get_json(path, params, api_key):
    """Fetch a Geoapify endpoint using its path, query parameters, and API key."""
    query = urlencode({**params, "apiKey": api_key})
    return _fetch_json(f"https://api.geoapify.com/{path}?{query}")


def _find_bank_candidates(location, bank_name, api_key):
    """Return nearby Geoapify bank listings, optionally filtered by bank name."""
    longitude = float(location["lon"])
    latitude = float(location["lat"])
    params = {
        "categories": "service.financial.bank",
        "filter": f"circle:{longitude},{latitude},500",
        "limit": 5,
    }

    if bank_name.strip():
        params["name"] = bank_name

    result = get_json("v2/places", params, api_key)
    candidates = []
    for feature in result.get("features", []):
        properties = feature.get("properties", {})
        candidates.append(
            {
                "name": properties.get("name", ""),
                "address": properties.get("formatted", ""),
                "place_id": properties.get("place_id", ""),
                "source": "https://www.geoapify.com/",
                "data_source": properties.get("datasource", {}).get(
                    "attribution", "OpenStreetMap contributors"
                ),
            }
        )

    return candidates


@mcp.tool()
def search_bank(bank_name: str, bank_address: str) -> dict:
    """Return bank candidates; bank_name may be empty."""
    api_key = os.getenv("GEOAPIFY_API_KEY", "")
    if not api_key:
        return {"status": "NOT_CONFIGURED", "candidates": []}

    if not bank_address.strip() or len(bank_name) > 200 or len(bank_address) > 500:
        return {"status": "INVALID_INPUT", "candidates": []}

    try:
        # Request two results so a second geocoding match can flag ambiguity.
        locations = get_json(
            "v1/geocode/search",
            {"text": bank_address, "format": "json", "limit": 2},
            api_key,
        ).get("results", [])

        if not locations:
            return {"status": "ADDRESS_NOT_FOUND", "candidates": []}

        confident_locations = [
            location
            for location in locations
            if location.get("rank", {}).get("confidence", 0) >= 0.8
        ]

        if len(confident_locations) != 1:
            return {"status": "ADDRESS_AMBIGUOUS", "candidates": []}

        location = confident_locations[0]
        searched_name = bank_name
        candidates = _find_bank_candidates(location, searched_name, api_key)

        if not candidates and searched_name.strip():
            searched_name = ""
            candidates = _find_bank_candidates(location, searched_name, api_key)

        return {
            "status": "CANDIDATES_FOUND" if candidates else "NO_MATCH",
            "searched_name": searched_name,
            "searched_address": bank_address,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "candidates": candidates,
            "limitation": (
                "Nearby matches require address comparison; "
                "no licensing check was performed."
            ),
        }
    except Exception as error:
        return {
            "status": "UNAVAILABLE",
            "error_type": type(error).__name__,
            "candidates": [],
        }


class _UnusableRateTable(ValueError):
    """Indicate that the provider returned an unusable USD rate table."""


def _rate_table_timestamp(table):
    """Return the update timestamp for a usable USD table or raise an error."""
    if not isinstance(table, dict):
        raise _UnusableRateTable

    timestamp = int(table["time_last_update_unix"])

    # Allow five minutes of clock skew and reject tables older than 72 hours.
    if (
        table.get("result") != "success"
        or table.get("base_code") != "USD"
        or not -300 <= time.time() - timestamp <= 72 * 3600
    ):
        raise _UnusableRateTable

    if not isinstance(table["rates"], dict):
        raise _UnusableRateTable

    return timestamp


@lru_cache(maxsize=2)
def rate_table(hour):
    """Fetch and validate a USD rate table before caching it by UTC epoch hour."""
    table = _fetch_json("https://open.er-api.com/v6/latest/USD")

    # lru_cache stores successful returns only, so failed fetches can be retried.
    _rate_table_timestamp(table)
    return table


@mcp.tool()
def get_exchange_rate(currency_code: str) -> dict:
    """Supply a rate only. The AI converts and compares the balance."""
    code = currency_code.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        return {"status": "INVALID_CODE"}

    if code == "USD":
        return {
            "status": "READY",
            "currency": "USD",
            "units_per_usd": 1,
            "rate_date": datetime.now(timezone.utc).date().isoformat(),
            "source": None,
        }

    try:
        table = rate_table(int(time.time() // 3600))
        try:
            timestamp = _rate_table_timestamp(table)
        except _UnusableRateTable:
            # A previously valid table can expire before the cache key changes.
            rate_table.cache_clear()
            raise

        rate = table["rates"].get(code)
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
            return {
                "status": "UNSUPPORTED_CURRENCY",
                "currency": code,
            }

        return {
            "status": "READY",
            "currency": code,
            "units_per_usd": rate,
            "rate_date": datetime.fromtimestamp(
                timestamp, timezone.utc
            ).date().isoformat(),
            "formula": "USD = original amount / units_per_usd",
            "source": "https://www.exchangerate-api.com",
        }
    except _UnusableRateTable:
        return {"status": "UNAVAILABLE"}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {"status": "UNAVAILABLE", "error_type": type(error).__name__}


if __name__ == "__main__":
    # The MCP client exchanges messages over this process's stdin and stdout.
    mcp.run(transport="stdio")