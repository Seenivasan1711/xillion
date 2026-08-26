"""
Data provider template — copy this to add a new historical data source
(e.g. DhanHQ, TrueData, TradingView for forex).

Steps:
1. cp data_providers/_template.py data_providers/my_provider.py
2. Rename MyDataProvider, fill in name/description/capabilities
3. Implement fetch_bars()
4. Click "Reload plugins" on the Strategies page — it appears in
   Settings → Data Providers automatically
5. If capabilities.requires_credentials=True, an API-key form appears there
   automatically too; your fetch_bars() receives the saved payload as
   `credentials`

Contract rules:
- Do NOT import any strategy modules.
- Raise a clear exception on failure (missing credentials, no broker
  connected, provider outage) rather than silently returning an empty list
  — an empty list reads as "no data in this range," which is misleading.
- Respect `timeframe` — if your provider only offers certain granularities
  (e.g. daily-only, like the free NSE bhavcopy provider), raise ValueError
  for anything else rather than silently ignoring the request.
"""

from datetime import date

from xillion.core.data_provider_base import DataProviderCapabilities, HistoricalDataProvider
from xillion.core.events import Bar


class MyDataProvider(HistoricalDataProvider):
    name = "My Provider"  # Must be unique across all loaded providers
    version = "0.1.0"
    description = "A brief description of what this data source is and its real limits."

    capabilities = DataProviderCapabilities(
        supports_equity=True,
        supports_futures=False,
        supports_options=False,
        supports_forex=False,
        requires_credentials=True,  # True → Settings shows an API-key form for this provider
        requires_broker=False,  # True → this provider piggybacks on a connected Broker instead (like Kite)
        max_lookback_days=None,  # Set a real number if the vendor has a hard limit
    )

    async def fetch_bars(
        self,
        symbol: str,
        exchange: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        *,
        instrument_type: str = "equity",
        credentials: dict | None = None,
        broker=None,
    ) -> list[Bar]:
        if self.capabilities.requires_credentials and not credentials:
            raise ValueError(
                f"{self.name} needs credentials — configure it under Settings → Data Providers"
            )

        # ── Your fetch + parse logic goes here ──────────────────────────────
        # api_key = credentials["api_key"]
        # rows = await your_http_call(...)
        # return [Bar(symbol=symbol, timeframe=timeframe, ts=..., open=..., high=..., low=..., close=..., volume=...) for row in rows]

        raise NotImplementedError(f"{self.name}.fetch_bars is a template — implement it")
