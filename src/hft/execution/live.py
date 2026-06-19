"""Live-Trading-Adapter (echte Börsenanbindung).

ACHTUNG — ECHTES GELD: Dieser Broker sendet echte Orders an eine Börse. Er ist
bewusst hinter mehreren Sicherungen verriegelt:

  * ``LiveBroker`` startet nur mit ``confirm_live=True``.
  * ``CcxtExchangeClient`` verbindet sich nur mit dem Testnet, es sei denn,
    ``allow_mainnet=True`` wird explizit gesetzt.

Der Adapter implementiert dasselbe :class:`~hft.execution.broker.Broker`-
Interface wie der Paper-Broker, sodass Strategie- und Risikocode unverändert
bleiben. Fills werden bei der Auftragserteilung und anschließend bei jedem Tick
(Polling von offenen Orders) mit der Börse abgeglichen.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from hft.core.types import Fill, Order, OrderStatus, OrderType, Tick
from hft.execution.broker import Broker

logger = logging.getLogger("hft.execution.live")


@runtime_checkable
class ExchangeClient(Protocol):
    """Minimale, normalisierte Börsenschnittstelle, die ``LiveBroker`` benötigt.

    Alle Methoden geben ein normalisiertes Dict zurück bzw. erwarten es:
    ``{"id": str, "status": "open"|"closed"|"canceled", "filled": float,
       "average": float, "fee_cost": float}``.
    """

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        ...

    def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        ...

    def fetch_order(self, exchange_order_id: str, symbol: str) -> dict[str, Any]:
        ...


class LiveBroker(Broker):
    """Leitet Orders an eine echte Börse weiter und gleicht Fills ab."""

    def __init__(
        self,
        client: ExchangeClient,
        *,
        confirm_live: bool = False,
        poll_on_tick: bool = True,
    ) -> None:
        super().__init__()
        if not confirm_live:
            raise RuntimeError(
                "LiveBroker sendet echte Orders. Zum Aktivieren confirm_live=True "
                "setzen — nur nach Tests im Testnet und mit engen Risikolimits."
            )
        self.client = client
        self.poll_on_tick = poll_on_tick
        self._orders: dict[int, Order] = {}  # unsere order_id -> Order
        self._exch_ids: dict[int, str] = {}  # unsere order_id -> Börsen-ID
        self._reported_filled: dict[int, float] = {}  # bereits gemeldete Menge
        self._reported_fee: dict[int, float] = {}  # bereits gemeldete Gebühr

    # -- Auftragserteilung --------------------------------------------------
    def submit(self, order: Order) -> None:
        order_type = "market" if order.order_type is OrderType.MARKET else "limit"
        try:
            resp = self.client.create_order(
                order.symbol,
                order.side.value,
                order_type,
                order.quantity,
                order.limit_price,
            )
        except Exception:  # noqa: BLE001 — Börsenfehler dürfen die Engine nicht töten
            order.status = OrderStatus.REJECTED
            logger.exception("Order %s von der Börse abgelehnt", order.order_id)
            return

        exch_id = str(resp.get("id"))
        self._orders[order.order_id] = order
        self._exch_ids[order.order_id] = exch_id
        self._reported_filled[order.order_id] = 0.0
        self._reported_fee[order.order_id] = 0.0
        self._reconcile(order, resp)

    def cancel(self, order_id: int) -> bool:
        exch_id = self._exch_ids.get(order_id)
        order = self._orders.get(order_id)
        if exch_id is None or order is None:
            return False
        try:
            ok = self.client.cancel_order(exch_id, order.symbol)
        except Exception:  # noqa: BLE001
            logger.exception("Stornierung von Order %s fehlgeschlagen", order_id)
            return False
        if ok and order.is_active:
            order.status = OrderStatus.CANCELLED
        return bool(ok)

    # -- Marktdaten / Abgleich ---------------------------------------------
    def on_tick(self, tick: Tick) -> None:
        if not self.poll_on_tick:
            return
        for order_id, order in list(self._orders.items()):
            if order.symbol == tick.symbol and order.is_active:
                try:
                    resp = self.client.fetch_order(self._exch_ids[order_id], order.symbol)
                except Exception:  # noqa: BLE001
                    logger.exception("Statusabfrage für Order %s fehlgeschlagen", order_id)
                    continue
                self._reconcile(order, resp)

    def _reconcile(self, order: Order, resp: dict[str, Any]) -> None:
        """Erzeugt inkrementelle Fills aus einem normalisierten Börsenstatus."""
        filled = float(resp.get("filled") or 0.0)
        avg = float(resp.get("average") or 0.0)
        status = resp.get("status")

        fill_delta = filled - self._reported_filled[order.order_id]
        if fill_delta > 1e-12:
            price = avg if avg > 0 else (order.limit_price or 0.0)
            fee_total = float(resp.get("fee_cost") or 0.0)
            fee_delta = max(0.0, fee_total - self._reported_fee[order.order_id])
            order.apply_fill(fill_delta, price)
            self._reported_filled[order.order_id] = filled
            self._reported_fee[order.order_id] = fee_total
            self._emit_fill(
                Fill(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=fill_delta,
                    price=price,
                    commission=fee_delta,
                )
            )

        if status in ("canceled", "cancelled") and order.is_active:
            order.status = OrderStatus.CANCELLED

    @property
    def open_orders(self) -> list[Order]:
        return [o for o in self._orders.values() if o.is_active]


class CcxtExchangeClient:
    """``ExchangeClient`` auf Basis von `ccxt` (z. B. Binance, Kraken, Coinbase).

    ``ccxt`` wird verzögert importiert, damit der restliche Stack ohne diese
    optionale Abhängigkeit läuft. Installation: ``pip install ccxt``.
    """

    def __init__(
        self,
        exchange_id: str,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        testnet: bool = True,
        allow_mainnet: bool = False,
        params: dict[str, Any] | None = None,
    ) -> None:
        try:
            import ccxt  # type: ignore
        except ImportError as exc:  # pragma: no cover - abhängigkeitsspezifisch
            raise ImportError(
                "Für Live-Trading wird ccxt benötigt: pip install ccxt"
            ) from exc

        if not testnet and not allow_mainnet:
            raise RuntimeError(
                "Verbindung zum Mainnet abgelehnt. Für echtes Geld allow_mainnet=True "
                "setzen — auf eigenes Risiko."
            )

        exchange_class = getattr(ccxt, exchange_id)
        self._ex = exchange_class(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                **(params or {}),
            }
        )
        if testnet and self._ex.has.get("sandbox"):
            self._ex.set_sandbox_mode(True)

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        raw = self._ex.create_order(symbol, order_type, side, quantity, price)
        return self._normalize(raw)

    def cancel_order(self, exchange_order_id: str, symbol: str) -> bool:
        self._ex.cancel_order(exchange_order_id, symbol)
        return True

    def fetch_order(self, exchange_order_id: str, symbol: str) -> dict[str, Any]:
        return self._normalize(self._ex.fetch_order(exchange_order_id, symbol))

    @staticmethod
    def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
        fee = raw.get("fee") or {}
        return {
            "id": raw.get("id"),
            "status": raw.get("status"),
            "filled": raw.get("filled") or 0.0,
            "average": raw.get("average") or raw.get("price") or 0.0,
            "fee_cost": (fee.get("cost") if isinstance(fee, dict) else 0.0) or 0.0,
        }
