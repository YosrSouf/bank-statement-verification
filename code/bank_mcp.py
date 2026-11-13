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


def get_json(path, params, api_key):
    # Encode query values so spaces and special characters remain valid in URLs.
    query = urlencode(
        {**params, "apiKey": api_key}
    )

    request = Request(
        f"https://api.geoapify.com/{path}?{query}",
        headers={
            # Identify the application making requests to the provider.
            "User-Agent": "BankStatementVerification/1.0"
        },
    )

    # Bound the wait so an unresponsive provider cannot stall the review indefinitely.
    with urlopen(request, timeout=15) as response:
        return json.load(response)


# Expose this function so the MCP client can request external bank evidence.
@mcp.tool()
def search_bank(bank_name: str, bank_address: str) -> dict:
    """Return bank candidates; bank_name may be empty."""

    # Keep the API key outside source code so deployments can supply their own.
    key = os.getenv("GEOAPIFY_API_KEY", "")

    # Distinguish missing configuration from a search that found no banks.
    if not key:
        return {
            "status": "NOT_CONFIGURED",
            "candidates": [],
        }

    # Require an address to anchor the search and limit oversized input.
    if (
        not bank_address.strip()
        or len(bank_name) > 200
        or len(bank_address) > 500
    ):
        return {
            "status": "INVALID_INPUT",
            "candidates": [],
        }

    try:
        locations = get_json(
            "v1/geocode/search",
            {
                "text": bank_address,
                "format": "json",
                # Request two results so multiple possible locations can be detected.
                "limit": 2,
            },
            key,
        ).get("results", [])

        # Avoid searching around a location that is ambiguous or low-confidence.
        if (
            len(locations) != 1
            or locations[0].get("rank", {}).get(
                "confidence", 0
            ) < 0.8
        ):
            return {
                "status": "ADDRESS_AMBIGUOUS",
                "candidates": [],
            }

        location = locations[0]
        longitude = float(location["lon"])
        latitude = float(location["lat"])

        # Nearby bank listings provide candidates, not proof of an exact address match.
        parameters = {
            "categories": "service.financial.bank",
            "filter": (
                f"circle:{longitude},{latitude},500"
            ),
            "limit": 5,
        }

        # Allow address-only searches when the statement's bank name is missing.
        if bank_name.strip():
            parameters["name"] = bank_name

        result = get_json(
            "v2/places",
            parameters,
            key,
        )

        candidates = []

        for feature in result.get("features", []):
            properties = feature.get("properties", {})

            # Keep comparison fields and source details so findings can be traced.
            candidates.append(
                {
                    "name": properties.get("name", ""),
                    "address": properties.get("formatted", ""),
                    "place_id": properties.get("place_id", ""),
                    "source": "https://www.geoapify.com/",
                    "data_source": properties.get(
                        "datasource", {}
                    ).get(
                        "attribution",
                        "OpenStreetMap contributors",
                    ),
                }
            )

        # Record the search context without presenting a listing as bank verification.
        return {
            "status": (
                "CANDIDATES_FOUND"
                if candidates
                else "NO_MATCH"
            ),
            "searched_name": bank_name,
            "searched_address": bank_address,
            "checked_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "candidates": candidates,
            "limitation": (
                "Nearby matches require address comparison; "
                "no licensing check was performed."
            ),
        }

    except Exception as error:
        # Report a failed lookup separately from a valid search with no matches.
        return {
            "status": "UNAVAILABLE",
            "error_type": type(error).__name__,
            "candidates": [],
        }


# Reuse responses for the same hour while retaining at most two cached tables.
@lru_cache(maxsize=2)
def rate_table(hour):
    # The hour argument changes the cache key; it is not needed in the request.
    request = Request(
        "https://open.er-api.com/v6/latest/USD",
        headers={
            "User-Agent": "BankStatementVerification/1.0"
        },
    )

    with urlopen(request, timeout=15) as response:
        return json.load(response)


@mcp.tool()
def get_exchange_rate(currency_code: str) -> dict:
    """Supply a rate only. The AI converts and compares the balance."""

    # Accept harmless formatting differences before checking the code's shape.
    code = currency_code.strip().upper()

    # This checks format only; the rate table determines currency support.
    if not re.fullmatch(r"[A-Z]{3}", code):
        return {"status": "INVALID_CODE"}

    # USD needs no external lookup because conversion to itself always uses 1.
    if code == "USD":
        return {
            "status": "READY",
            "currency": "USD",
            "units_per_usd": 1,
            "rate_date": datetime.now(
                timezone.utc
            ).date().isoformat(),
            "source": None,
        }

    try:
        # A new hourly key triggers a fetch without requesting a table for every review.
        table = rate_table(
            int(time.time() // 3600)
        )

        timestamp = int(
            table["time_last_update_unix"]
        )

        # Require USD-based data no older than 72 hours, allowing 5 minutes of clock skew.
        if (
            table.get("result") != "success"
            or table.get("base_code") != "USD"
            or not -300 <= time.time() - timestamp <= 72 * 3600
        ):
            return {"status": "UNAVAILABLE"}

        rate = table["rates"].get(code)

        # A missing or nonpositive rate cannot support a meaningful conversion.
        if not isinstance(rate, (int, float)) or rate <= 0:
            return {
                "status": "UNSUPPORTED_CURRENCY",
                "currency": code,
            }

        return {
            "status": "READY",
            "currency": code,
            "units_per_usd": rate,
            # Use the provider's update date so cached data is not presented as newer.
            "rate_date": datetime.fromtimestamp(
                timestamp,
                timezone.utc,
            ).date().isoformat(),
            # Rates express foreign units per USD, so conversion to USD uses division.
            "formula": (
                "USD = original amount / units_per_usd"
            ),
            "source": "https://www.exchangerate-api.com",
        }

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        # Return an explicit failure when network or response problems prevent a rate.
        return {
            "status": "UNAVAILABLE",
            "error_type": type(error).__name__,
        }


# Start only when executed directly, allowing imports without launching the server.
if __name__ == "__main__":
    # Use standard input/output for communication with the MCP client process.
    mcp.run(transport="stdio")