#!/usr/bin/env python3
"""
EPO OPS MCP Server — bridges Claude Code to the EPO Open Patent Services API v3.2.

Provides 13 MCP tools for global patent search, retrieval, family/legal/register
lookups, CPC classification, patent number conversion, and quota monitoring.

Authentication: OAuth2 client credentials (Consumer Key + Consumer Secret).
Credentials are read in this priority order:
  1. Local JSON file (ops_credentials.json in the same directory as this script)
  2. OPS_CONSUMER_KEY / OPS_CONSUMER_SECRET environment variables
  3. OPS_CREDENTIALS_FILE env var (custom path to a JSON credentials file)

The JSON file format (ops_credentials.json):
{
  "OPS_CONSUMER_KEY": "your_consumer_key",
  "OPS_CONSUMER_SECRET": "your_consumer_secret"
}

Credentials are re-read on every tool call, so editing ops_credentials.json
takes effect immediately — no need to restart Claude Code.

Usage:
  python ops_mcp_server.py             # Start MCP server (stdio transport)
  python ops_mcp_server.py --test      # Run connectivity self-test
"""

from __future__ import annotations

import os
import sys
import time
import json
import base64
import argparse
import logging
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPS_BASE_URL = "https://ops.epo.org/3.2/rest-services"
OPS_AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"

# Token refresh buffer: refresh when fewer than this many seconds remain
TOKEN_BUFFER_SECONDS = 120  # 2 min — EPO tokens are typically ~20 min

# Default range for search results
DEFAULT_RANGE = "1-25"

# Logger
logger = logging.getLogger("epo-ops-mcp")

# ---------------------------------------------------------------------------
# Token Manager
# ---------------------------------------------------------------------------

class OpsTokenManager:
    """Obtains and caches OAuth2 access tokens for EPO OPS."""

    def __init__(self, consumer_key: str, consumer_secret: str) -> None:
        credentials = f"{consumer_key}:{consumer_secret}"
        self._basic_auth = base64.b64encode(credentials.encode()).decode()
        self._token: str | None = None
        self._expires_at: float = 0.0  # epoch seconds

    async def get_token(self, client: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if necessary."""
        now = time.time()
        if self._token and (now + TOKEN_BUFFER_SECONDS) < self._expires_at:
            return self._token

        logger.info("Requesting new OPS access token...")
        response = await client.post(
            OPS_AUTH_URL,
            headers={
                "Authorization": f"Basic {self._basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            content="grant_type=client_credentials",
        )
        response.raise_for_status()
        data = response.json()

        self._token = data["access_token"]
        # EPO returns expires_in in seconds (typical)
        expires_in = data.get("expires_in", 1200)
        self._expires_at = now + int(expires_in)

        logger.info("Token obtained — expires in %s seconds", expires_in)
        return self._token

# ---------------------------------------------------------------------------
# OPS API Client
# ---------------------------------------------------------------------------

class OpsClient:
    """Async HTTP client wrapper for EPO OPS API."""

    def __init__(self, token_manager: OpsTokenManager) -> None:
        self._tm = token_manager
        self._client: httpx.AsyncClient | None = None
        # Last throttling info (exposed via ops_throttle_status)
        self.last_throttle_headers: dict[str, str] = {}
        self.last_response_status: int = 0
        self.last_response_url: str = ""

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OpsClient not initialised — call start() first")
        return self._client

    async def start(self) -> None:
        """Create the shared httpx client (call once at startup)."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_auth(self) -> None:
        """Ensure a valid token is on the shared client."""
        token = await self._tm.get_token(self.client)
        self.client.headers["Authorization"] = f"Bearer {token}"

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an authenticated GET request to OPS and return parsed JSON."""
        await self._ensure_auth()
        url = f"{OPS_BASE_URL}{path}"

        try:
            resp = await self.client.get(url, params=params)
        except httpx.HTTPError:
            # Token may have been invalidated; retry once with fresh token
            token = await self._tm.get_token(self.client)
            self.client.headers["Authorization"] = f"Bearer {token}"
            resp = await self.client.get(url, params=params)

        return self._handle_response(resp, url)

    async def post(
        self, path: str, body: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated POST request to OPS and return parsed JSON."""
        await self._ensure_auth()
        url = f"{OPS_BASE_URL}{path}"

        try:
            resp = await self.client.post(
                url, content=body, params=params,
                headers={"Content-Type": "text/plain"},
            )
        except httpx.HTTPError:
            token = await self._tm.get_token(self.client)
            self.client.headers["Authorization"] = f"Bearer {token}"
            resp = await self.client.post(
                url, content=body, params=params,
                headers={"Content-Type": "text/plain"},
            )

        return self._handle_response(resp, url)

    def _handle_response(self, resp: httpx.Response, url: str) -> dict[str, Any]:
        """Record throttle info and return structured result."""
        # Capture throttle headers
        self.last_throttle_headers = {}
        for key in ("X-Throttling-Control", "X-IndividualQuotaPerHour-Used",
                     "X-RegisteredQuotaPerWeek-Used"):
            if key in resp.headers:
                self.last_throttle_headers[key] = resp.headers[key]

        self.last_response_status = resp.status_code
        self.last_response_url = url

        # Check for errors
        if resp.status_code == 403:
            return {
                "error": "Fair Use policy violation (HTTP 403). "
                         "Reduce request frequency or wait for quota reset.",
                "status": 403,
            }
        if resp.status_code == 404:
            return {
                "error": "Patent or resource not found (HTTP 404). Check the number/query.",
                "status": 404,
            }
        if resp.status_code >= 400:
            detail = resp.text[:2000]
            try:
                detail = resp.json()
            except Exception:
                pass
            return {
                "error": f"OPS API error (HTTP {resp.status_code})",
                "detail": detail,
                "status": resp.status_code,
            }

        # Parse JSON — OPS returns JSON when Accept header is set
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text[:5000], "content_type": resp.headers.get("content-type", "")}

# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------

ops: OpsClient | None = None
tm: OpsTokenManager | None = None
_last_credentials_hash: str = ""  # track changes to hot-reload

# ---------------------------------------------------------------------------
# Credentials loader — priority: local JSON > env var OPS_CREDENTIALS_FILE > env vars
# ---------------------------------------------------------------------------

def _default_credentials_path() -> str:
    """Default location of credentials file: next to this script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "ops_credentials.json")


def _load_credentials_from_file(path: str) -> tuple[str, str] | None:
    """Try to load credentials from a JSON file. Returns (key, secret) or None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        key = str(data.get("OPS_CONSUMER_KEY", "")).strip()
        secret = str(data.get("OPS_CONSUMER_SECRET", "")).strip()
        if key and secret:
            logger.info("Credentials loaded from %s", path)
            return key, secret
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError):
        pass
    return None


def _get_credentials() -> tuple[str, str]:
    """Resolve credentials: file first, then env vars.

    Check order:
      1. OPS_CREDENTIALS_FILE env var → custom JSON file path
      2. ops_credentials.json in the script directory
      3. OPS_CONSUMER_KEY / OPS_CONSUMER_SECRET env vars
    """
    # 1. Custom file path via env var
    custom_path = os.getenv("OPS_CREDENTIALS_FILE", "")
    if custom_path:
        result = _load_credentials_from_file(custom_path)
        if result:
            return result

    # 2. Default file next to script
    result = _load_credentials_from_file(_default_credentials_path())
    if result:
        return result

    # 3. Environment variables (backward-compatible)
    key = os.getenv("OPS_CONSUMER_KEY", "")
    secret = os.getenv("OPS_CONSUMER_SECRET", "")
    if key and secret:
        logger.info("Credentials loaded from environment variables")
        return key, secret

    raise RuntimeError(
        "OPS credentials not found. Create ops_credentials.json next to this "
        "script with OPS_CONSUMER_KEY and OPS_CONSUMER_SECRET, or set the "
        "environment variables OPS_CONSUMER_KEY / OPS_CONSUMER_SECRET."
    )

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="epo-ops",
    instructions=(
        "EPO Open Patent Services (OPS) API v3.2.\n"
        "Use this server to search and retrieve global patent data:\n"
        "- ops_search: CQL patent search\n"
        "- ops_get_biblio: bibliographic data retrieval\n"
        "- ops_get_abstract: patent abstract\n"
        "- ops_get_fulltext: description / claims full text\n"
        "- ops_get_family: INPADOC patent family\n"
        "- ops_get_equivalents: DOCDB simple family\n"
        "- ops_get_legal: legal status events\n"
        "- ops_get_register: EPO register (procedural data)\n"
        "- ops_get_images: patent image inquiry\n"
        "- ops_cpc_lookup: CPC classification hierarchy\n"
        "- ops_cpc_search: CPC keyword search\n"
        "- ops_convert_number: patent number format conversion\n"
        "- ops_throttle_status: rate-limit / quota status"
    ),
)

# ---------------------------------------------------------------------------
# Helper: lazy-initialise the shared client on first tool call
# ---------------------------------------------------------------------------

async def _ensure_client() -> OpsClient:
    """Return the shared OpsClient, creating or re-creating it as needed.

    Credentials are re-read on every call, so editing ops_credentials.json
    takes effect immediately — no need to restart Claude Code.
    """
    global ops, tm, _last_credentials_hash

    key, secret = _get_credentials()
    creds_hash = f"{key}:{secret}"

    # If credentials changed (or first call), recreate token manager + client
    if ops is None or tm is None or creds_hash != _last_credentials_hash:
        if ops is not None:
            logger.info("Credentials changed — reinitialising OPS client")
            await ops.close()
        tm = OpsTokenManager(key, secret)
        ops = OpsClient(tm)
        await ops.start()
        _last_credentials_hash = creds_hash
        logger.info("OPS client initialised")

    return ops


def _error_result(msg: str, **extra: Any) -> dict[str, Any]:
    return {"error": msg, **extra}

# ===========================================================================
#  MCP Tools — Search & Retrieval
# ===========================================================================

@mcp.tool(
    name="ops_search",
    description=(
        "Search EPO's global patent database using CQL (Contextual Query Language).\n"
        "CQL field codes: ti (title), ab (abstract), pa/applicant (applicant), "
        "in/inventor (inventor), pd (publication date), num (publication number), "
        "cl (classification/IPC), cpc (CPC class).\n"
        "Boolean: AND, OR, NOT. Range: pd within \"2020 2024\".\n"
        "Examples: 'pa=Microsoft AND ti=quantum', 'cl=H01L', 'num=EP1000000'."
    ),
)
async def ops_search(
    query: str,
    range: str = DEFAULT_RANGE,
) -> dict[str, Any]:
    """
    Keyword / CQL patent search.

    Args:
        query: CQL search query string.
        range: Result range, e.g. "1-25" (default) or "1-100".
    """
    c = await _ensure_client()
    result = await c.get("/published-data/search", {"q": query, "Range": range})
    return result


@mcp.tool(
    name="ops_get_biblio",
    description=(
        "Retrieve full bibliographic data for a patent by publication/application/priority number.\n"
        "Includes: title, abstract (short), inventors, applicants, IPC/CPC classes, "
        "priority claims, publication info, and citations."
    ),
)
async def ops_get_biblio(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
) -> dict[str, Any]:
    """
    Bibliographic data retrieval.

    Args:
        type: Reference type — "publication", "application", or "priority".
        format: Reference format — "epodoc" or "docdb".
        number: Patent reference number (e.g. "EP1000000", "US20240001234A1").
    """
    c = await _ensure_client()
    result = await c.get(f"/published-data/{type}/{format}/{number}/biblio")
    return result


@mcp.tool(
    name="ops_get_abstract",
    description=(
        "Retrieve the patent abstract text. "
        "Returns the abstract as published by the patent office."
    ),
)
async def ops_get_abstract(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
) -> dict[str, Any]:
    """
    Abstract retrieval.

    Args:
        type: Reference type — "publication", "application", or "priority".
        format: Reference format — "epodoc" or "docdb".
        number: Patent reference number.
    """
    c = await _ensure_client()
    result = await c.get(f"/published-data/{type}/{format}/{number}/abstract")
    return result


@mcp.tool(
    name="ops_get_fulltext",
    description=(
        "Retrieve the full text of a patent's description OR claims.\n"
        "Use part='description' for the patent specification/description.\n"
        "Use part='claims' for the claims only."
    ),
)
async def ops_get_fulltext(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
    part: str = "description",
) -> dict[str, Any]:
    """
    Full-text retrieval (description or claims).

    Args:
        type: Reference type — "publication", "application", or "priority".
        format: Reference format — "epodoc" or "docdb".
        number: Patent reference number.
        part: Which part to retrieve — "description" or "claims".
    """
    if part not in ("description", "claims"):
        return _error_result("part must be 'description' or 'claims'")
    c = await _ensure_client()
    result = await c.get(f"/published-data/{type}/{format}/{number}/{part}")
    return result


# ===========================================================================
#  MCP Tools — Relationships (Family, Equivalents, Legal)
# ===========================================================================

@mcp.tool(
    name="ops_get_family",
    description=(
        "Retrieve the INPADOC extended patent family.\n"
        "optionally with bibliographic data and/or legal status for each family member.\n"
        "Use constituents parameter to add extra data:\n"
        "  - empty/omitted: family members only\n"
        "  - 'biblio': family + bibliographic data per member\n"
        "  - 'legal': family + legal status per member"
    ),
)
async def ops_get_family(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
    constituents: str = "",
) -> dict[str, Any]:
    """
    INPADOC family retrieval.

    Args:
        type: Reference type — "publication", "application", or "priority".
        format: Reference format — "epodoc" or "docdb".
        number: Patent reference number.
        constituents: Extra data — "" (family only), "biblio", or "legal".
    """
    c = await _ensure_client()
    suffix = ""
    if constituents in ("biblio", "legal"):
        suffix = f"/{constituents}"
    result = await c.get(f"/family/{type}/{format}/{number}{suffix}")
    return result


@mcp.tool(
    name="ops_get_equivalents",
    description=(
        "Retrieve the DOCDB simple patent family (equivalents).\n"
        "This returns a narrower set of directly equivalent patents, "
        "as opposed to the broader INPADOC extended family from ops_get_family."
    ),
)
async def ops_get_equivalents(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
) -> dict[str, Any]:
    """
    DOCDB simple family (equivalents).

    Args:
        type: Reference type — "publication", "application", or "priority".
        format: Reference format — "epodoc" or "docdb".
        number: Patent reference number.
    """
    c = await _ensure_client()
    result = await c.get(f"/published-data/{type}/{format}/{number}/equivalents")
    return result


@mcp.tool(
    name="ops_get_legal",
    description=(
        "Retrieve the legal status events for a patent.\n"
        "Returns a chronological list of legal events (grants, lapsing, "
        "oppositions, fee payments, etc.) from the INPADOC legal status database."
    ),
)
async def ops_get_legal(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
) -> dict[str, Any]:
    """
    Legal status retrieval.

    Args:
        type: Reference type — "publication", "application", or "priority".
        format: Reference format — "epodoc" or "docdb".
        number: Patent reference number.
    """
    c = await _ensure_client()
    result = await c.get(f"/legal/{type}/{format}/{number}")
    return result


# ===========================================================================
#  MCP Tools — Register
# ===========================================================================

@mcp.tool(
    name="ops_get_register",
    description=(
        "Retrieve the EPO patent register for a given patent.\n"
        "The register contains procedural data: examination progress, "
        "grant status, oppositions, and Unitary Patent information.\n"
        "Use this to check where a patent application stands in the EPO process."
    ),
)
async def ops_get_register(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
) -> dict[str, Any]:
    """
    EPO Register retrieval.

    Args:
        type: Reference type — "publication" or "application".
        format: Reference format — "epodoc" (required for register).
        number: Patent reference number (must be an EP document).
    """
    c = await _ensure_client()
    result = await c.get(f"/register/{type}/{format}/{number}/biblio")
    return result


# ===========================================================================
#  MCP Tools — Classification
# ===========================================================================

@mcp.tool(
    name="ops_cpc_lookup",
    description=(
        "Look up the Cooperative Patent Classification (CPC) hierarchy.\n"
        "Given a CPC symbol (e.g. 'A01B', 'G06F3'), returns the classification "
        "definition, subclasses, and optionally ancestors/descendants.\n"
        "Use depth to control how many levels of subclasses to return."
    ),
)
async def ops_cpc_lookup(
    cpc_class: str = "A01B",
    ancestors: bool = False,
    navigation: bool = False,
    depth: str = "0",
) -> dict[str, Any]:
    """
    CPC classification lookup.

    Args:
        cpc_class: CPC class symbol, e.g. "A01B", "G06F3", "H01L29".
        ancestors: If True, include ancestor classifications.
        navigation: If True, include navigation data.
        depth: How deep to traverse — "0", "1", "2", "3", or "all".
    """
    c = await _ensure_client()
    params: dict[str, Any] = {}
    if ancestors:
        params["ancestors"] = "true"
    if navigation:
        params["navigation"] = "true"
    if depth != "0":
        params["depth"] = depth
    result = await c.get(f"/classification/cpc/{cpc_class}", params or None)
    return result


@mcp.tool(
    name="ops_cpc_search",
    description=(
        "Search for relevant CPC classification codes by keyword.\n"
        "Returns CPC symbols and their definitions that match the query.\n"
        "Use this to find the right classification for a technology area "
        "before doing a full patent search."
    ),
)
async def ops_cpc_search(
    query: str = "laser",
) -> dict[str, Any]:
    """
    CPC keyword search.

    Args:
        query: Keyword or phrase to search CPC definitions, e.g. "semiconductor laser".
    """
    c = await _ensure_client()
    result = await c.get("/classification/cpc/search", {"q": query})
    return result


# ===========================================================================
#  MCP Tools — Images
# ===========================================================================

@mcp.tool(
    name="ops_get_images",
    description=(
        "Retrieve information about available images (drawings/figures) for a patent.\n"
        "Returns a list of image references. Use the image paths returned to "
        "determine which figures are available.\n"
        "Note: actual image binary download requires a separate HTTP request; "
        "this tool returns metadata about available images."
    ),
)
async def ops_get_images(
    type: str = "publication",
    format: str = "epodoc",
    number: str = "EP1000000",
) -> dict[str, Any]:
    """
    Image inquiry.

    Args:
        type: Reference type — "publication", "application", or "priority".
        format: Reference format — "docdb" or "epodoc".
        number: Patent reference number.
    """
    c = await _ensure_client()
    result = await c.get(f"/published-data/{type}/{format}/{number}/images")
    return result


# ===========================================================================
#  MCP Tools — Number Conversion
# ===========================================================================

@mcp.tool(
    name="ops_convert_number",
    description=(
        "Convert a patent number between different formats.\n"
        "Supports: original → docdb, original → epodoc, docdb → original, etc.\n"
        "Useful when you have a patent number in one format and need it in another "
        "for use with other OPS tools."
    ),
)
async def ops_convert_number(
    type: str = "publication",
    input_format: str = "original",
    number: str = "EP1000000",
    output_format: str = "docdb",
) -> dict[str, Any]:
    """
    Patent number format conversion.

    Args:
        type: Reference type — "publication", "application", or "priority".
        input_format: Format of the input number — "original", "docdb", or "epodoc".
        number: Patent number to convert.
        output_format: Desired output format — "original", "docdb", or "epodoc".
    """
    c = await _ensure_client()
    result = await c.get(
        f"/number-service/{type}/{input_format}/{number}/{output_format}"
    )
    return result


# ===========================================================================
#  MCP Tools — Throttle / Quota Status
# ===========================================================================

@mcp.tool(
    name="ops_throttle_status",
    description=(
        "Check the current EPO OPS API usage quota and throttling status.\n"
        "Returns the last known throttle state from the most recent API call, "
        "including hourly and weekly quota consumption. "
        "Use this before launching heavy search jobs to avoid 403 errors."
    ),
)
async def ops_throttle_status() -> dict[str, Any]:
    """Return current OPS throttling / quota status."""
    c = await _ensure_client()
    return {
        "last_response_status": c.last_response_status,
        "last_response_url": c.last_response_url,
        "throttle_headers": c.last_throttle_headers,
        "note": (
            "These values reflect the most recent API call. "
            "Make a search request first if values are empty."
        ),
    }


# ===========================================================================
#  Self-test
# ===========================================================================

async def run_self_test() -> int:
    """Run a connectivity self-test and return exit code (0 = success)."""
    print("=== EPO OPS MCP Server — Connectivity Test ===\n")

    # Use the same credential resolution as the server
    try:
        consumer_key, consumer_secret = _get_credentials()
    except RuntimeError as e:
        print(f"[FAIL] {e}")
        return 1

    tm_obj = OpsTokenManager(consumer_key, consumer_secret)
    c = OpsClient(tm_obj)
    await c.start()

    failures = 0

    # 1. Authenticate
    print("[1/4] Authenticating...")
    try:
        token = await tm_obj.get_token(c.client)
        print(f"  [OK] Token obtained ({len(token)} chars)")
    except Exception as e:
        print(f"  [FAIL] Auth failed: {e}")
        failures += 1

    # 2. Fetch biblio
    print("[2/4] Fetching EP1000000 biblio...")
    try:
        result = await c.get("/published-data/publication/epodoc/EP1000000/biblio")
        text = json.dumps(result)
        print(f"  [OK] Got {len(text)} bytes")
    except Exception as e:
        print(f"  [FAIL] Failed: {e}")
        failures += 1

    # 3. Search
    print("[3/4] Searching 'pa=IBM'...")
    try:
        result = await c.get("/published-data/search", {"q": "pa=IBM", "Range": "1-5"})
        text = json.dumps(result)
        print(f"  [OK] Got {len(text)} bytes")
    except Exception as e:
        print(f"  [FAIL] Failed: {e}")
        failures += 1

    # 4. Throttle status
    print("[4/4] Throttle status:")
    headers = c.last_throttle_headers
    if headers:
        for k, v in headers.items():
            print(f"  {k}: {v}")
    else:
        print("  (no throttle headers returned)")

    await c.close()

    if failures == 0:
        print(f"\n=== All tests passed ===")
        return 0
    else:
        print(f"\n=== {failures} test(s) failed ===")
        return 1


# ===========================================================================
#  Main entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="EPO OPS MCP Server")
    parser.add_argument(
        "--test", action="store_true",
        help="Run connectivity self-test and exit",
    )
    args = parser.parse_args()

    if args.test:
        import asyncio
        code = asyncio.run(run_self_test())
        sys.exit(code)

    # MCP server mode — env vars validated lazily on first tool call
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
