"""
Historical data provider plugin contract. Same drop-a-file pattern as
strategies/ and brokers/ (see plugin_loader.py): every file in
data_providers/ must export exactly one class inheriting from
HistoricalDataProvider, and it's auto-discovered -- no registry edits needed.

Two shapes of provider exist:
  - Standalone providers fetch bars directly, using either no credentials
    (e.g. a free NSE bhavcopy provider) or their own API key
    (capabilities.requires_credentials=True -- e.g. TrueData, DhanHQ).
  - Broker-backed providers piggyback on an already-connected Broker
    instance instead of re-implementing that broker's auth (e.g. Kite,
    which reuses whatever Zerodha connection is already live rather than
    managing a second, separate authenticated session).
"""
from abc import ABC
from dataclasses import dataclass
from datetime import date
from typing import Optional

from xillion.core.events import Bar


@dataclass
class DataProviderCapabilities:
    """Declares what a provider supports. Drives Settings UI badges and
    which providers make sense to offer for a given instrument type."""
    supports_equity: bool = True
    supports_futures: bool = False
    supports_options: bool = False
    supports_forex: bool = False
    requires_credentials: bool = True
    requires_broker: bool = False       # True for providers that piggyback on a connected Broker (e.g. Kite)
    max_lookback_days: Optional[int] = None  # None = no known hard limit


class HistoricalDataProvider(ABC):
    """Plugin contract for a historical OHLCV data source."""

    name: str = ""
    version: str = "0.0.1"
    description: str = ""
    capabilities: DataProviderCapabilities = DataProviderCapabilities()

    # (payload_key, label, input_type) for the Settings credential form.
    # payload_key must be "api_key" or "api_secret" -- those are the two
    # slots credentials get stored under; override the labels/input_type
    # when a provider's actual fields aren't a generic key/secret pair
    # (e.g. DhanHQ needs an access token + client ID, not "key"/"secret").
    credential_fields: list[tuple[str, str, str]] = [
        ("api_key", "API key", "text"),
        ("api_secret", "API secret", "password"),
    ]

    async def fetch_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "equity",
        credentials: Optional[dict] = None,
        broker=None,
    ) -> list[Bar]:
        """Fetch historical OHLCV bars for one instrument over a date range.

        `credentials` -- decrypted payload from DataProviderCredential, for
        providers with their own API key (None if requires_credentials is
        False for this provider).
        `broker` -- an already-connected Broker instance, for providers with
        capabilities.requires_broker=True (e.g. Kite reusing the live
        Zerodha connection instead of a second auth flow). None if no
        matching broker is connected -- such providers should raise a clear
        error rather than fail silently.
        """
        raise NotImplementedError
