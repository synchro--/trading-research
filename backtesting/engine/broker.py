"""Single-position broker: cash, qty, stop vs bar.low, costs on every fill."""
from __future__ import annotations

from backtesting.engine.types import Fill, Position, Trade


class Broker:
    def __init__(
        self,
        cash: float,
        commission_bps: float = 10.0,
        slippage_bps: float = 5.0,
    ):
        self.cash = cash
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.position: Position | None = None
        self.fills: list[Fill] = []
        self.trades: list[Trade] = []
        self._entry_bar_index = 0
        self._bar_index = 0

    def mark_bar(self, i: int) -> None:
        self._bar_index = i

    def equity(self, close: float) -> float:
        if self.position is None:
            return self.cash
        return self.cash + self.position.qty * close

    def _apply_slip(self, px: float, side: str) -> float:
        slip = self.slippage_bps / 10_000.0
        return px * (1.0 + slip) if side == "buy" else px * (1.0 - slip)

    def _commission(self, notional: float) -> float:
        return abs(notional) * (self.commission_bps / 10_000.0)

    def buy(self, t: str, px: float, qty: float, initial_risk: float) -> None:
        if self.position is not None or qty <= 0 or initial_risk <= 0:
            return
        fill_px = self._apply_slip(px, "buy")
        notional = fill_px * qty
        comm = self._commission(notional)
        total = notional + comm
        if total > self.cash:
            qty = max(0.0, (self.cash * 0.99) / (fill_px * (1.0 + self.commission_bps / 10_000.0)))
            if qty <= 0:
                return
            notional = fill_px * qty
            comm = self._commission(notional)
            total = notional + comm
            if total > self.cash:
                return
        self.cash -= total
        trail = fill_px - initial_risk
        self.position = Position(
            qty=qty,
            entry_px=fill_px,
            entry_time=t,
            initial_risk=initial_risk,
            trail=trail,
        )
        self._entry_bar_index = self._bar_index
        self.fills.append(Fill(t=t, side="buy", px=fill_px, qty=qty, reason="entry"))

    def sell(self, t: str, px: float, reason: str) -> None:
        pos = self.position
        if pos is None:
            return
        fill_px = self._apply_slip(px, "sell")
        notional = fill_px * pos.qty
        comm = self._commission(notional)
        self.cash += notional - comm
        pnl = (fill_px - pos.entry_px) * pos.qty - comm - self._commission(pos.entry_px * pos.qty)
        r_mult = (fill_px - pos.entry_px) / pos.initial_risk if pos.initial_risk else 0.0
        self.trades.append(
            Trade(
                entry_time=pos.entry_time,
                entry_px=pos.entry_px,
                exit_time=t,
                exit_px=fill_px,
                qty=pos.qty,
                r_multiple=r_mult,
                pnl=pnl,
                reason=reason,
                hold_bars=max(0, self._bar_index - self._entry_bar_index),
            )
        )
        self.fills.append(Fill(t=t, side="sell", px=fill_px, qty=pos.qty, reason=reason))
        self.position = None

    def stop_fill_price(self, bar_open: float, bar_low: float) -> float | None:
        """If live trail is hit this bar, return fill price min(open, trail)."""
        pos = self.position
        if pos is None:
            return None
        if bar_low <= pos.trail:
            return min(bar_open, pos.trail)
        return None
