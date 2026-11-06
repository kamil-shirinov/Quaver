"""Faber's family on the nine Select Sector SPDR ETFs, as a QuantConnect LEAN algorithm.

This file runs only inside QuantConnect: it imports AlgorithmImports, which exists only there.
The arithmetic is in logic.py, which is pure Python and tested outside LEAN.

Parameters (set in the QuantConnect project):
    mode  family, benchmark or smoke. smoke runs the family code path on SPY, TLT, GLD and IWM.
    end   the last holding month, YYYY-MM.

Timing, in LEAN terms. Data is daily, adjusted for splits and dividends, and
settings.daily_precise_end_time is on, so each daily bar ends at 16:00 ET.
    Signal  A scheduled event fires 10 minutes after the close of each month's last trading
            day (date_rules.month_end, time_rules.after_market_close). LEAN runs it before the
            next day's bar is applied, so the portfolio is valued at that day's closes. The
            event checks that every ETF's last bar ended that day, then reads month-end
            closes from a daily history request that ends at the event time.
    Orders  The event submits market-on-open orders, sells first. They fill when the next
            trading day's daily bar arrives, stamped 16:00 ET that day, at that bar's open
            (EquityFillModel.MarketOnOpenFill uses TradeBar.Open). on_order_event raises if a
            fill lands on any other day or at any other price, or if an order is invalid.
"""

from datetime import date, datetime

from AlgorithmImports import (
    AccountType,
    BrokerageName,
    CashAmount,
    DataNormalizationMode,
    EquityFillModel,
    FeeModel,
    NullSlippageModel,
    OrderEvent,
    OrderFee,
    OrderFeeParameters,
    OrderStatus,
    QCAlgorithm,
    Resolution,
    TradeBar,
)

import logic

# LEAN's default for US equities on a margin account. It lets the buy orders, submitted while
# the positions they replace are still held, pass the buying-power check at submission. The
# targets themselves never use it: they add up to at most (1 - CASH_BUFFER) of the portfolio.
LEVERAGE = 2.0
MINUTES_AFTER_CLOSE = 10


class TradedValueFeeModel(FeeModel):
    """FEE_RATE of traded value. A market-on-open fill is at the bar's open, security.open."""

    def get_order_fee(self, parameters: OrderFeeParameters) -> OrderFee:
        traded = abs(parameters.order.quantity) * parameters.security.open
        return OrderFee(CashAmount(logic.fee(traded), "USD"))


def _month_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


class FaberSectorFamily(QCAlgorithm):
    def initialize(self) -> None:
        self._run = logic.run_settings(self.get_parameter("mode"), self.get_parameter("end"))
        base = self._run.base
        self.set_start_date(int(base[:4]), int(base[5:]), 1)
        # A week into the month after end, so the end month's month-end event has fired.
        after = logic.add_months(self._run.end, 1)
        self.set_end_date(int(after[:4]), int(after[5:]), 7)
        self.set_cash(logic.INITIAL_CASH)
        self.settings.daily_precise_end_time = True
        self.set_brokerage_model(BrokerageName.DEFAULT, AccountType.MARGIN)

        self._symbols = []
        for ticker in self._run.tickers:
            security = self.add_equity(
                ticker,
                Resolution.DAILY,
                leverage=LEVERAGE,
                data_normalization_mode=DataNormalizationMode.ADJUSTED,
            )
            security.set_fee_model(TradedValueFeeModel())
            security.set_fill_model(EquityFillModel())
            security.set_slippage_model(NullSlippageModel.INSTANCE)
            self._symbols.append(security.symbol)
        anchor = self._symbols[0]
        self.set_benchmark(anchor)
        self.schedule.on(
            self.date_rules.month_end(anchor),
            self.time_rules.after_market_close(anchor, MINUTES_AFTER_CLOSE),
            self._month_end,
        )

        self._months: list[str] = []
        self._values: list[float] = []
        self._min_cash = float("inf")
        self._fees = 0.0
        self._submitted = 0
        self._filled = 0
        self._fill_day: date | None = None

    def _month_end(self) -> None:
        day = self.time.date()
        month = _month_of(day)
        if month < self._run.base or month > self._run.end:
            return
        if self._months and month != logic.add_months(self._months[-1], 1):
            raise RuntimeError(f"month-end event for {month} follows {self._months[-1]}")
        for symbol in self._symbols:
            bar = self.securities[symbol].get_last_data()
            if bar is None or bar.end_time.date() != day:
                raise RuntimeError(f"{symbol} has no bar ending {day} at the month-end event")

        self._months.append(month)
        self._values.append(float(self.portfolio.total_portfolio_value))
        if month > self._run.base:
            # Cash only moves on fills, so this is the cash left after this month's orders.
            self._min_cash = min(self._min_cash, float(self.portfolio.cash))
        if month == self._run.end:
            return  # the last holding month: value it, trade no more

        closes = self._closes(day, month)
        t = len(closes) - 1
        if self._run.follows_family:
            weights = logic.family_weights(closes, t)
        else:
            weights = logic.benchmark_weights(len(self._symbols))
        held = [int(self.portfolio[symbol].quantity) for symbol in self._symbols]
        quantities = logic.order_quantities(weights, self._values[-1], closes[t], held)
        for i in logic.submission_order(quantities):
            self.market_on_open_order(self._symbols[i], quantities[i], tag=month)
            self._submitted += 1
        exchange = self.securities[self._symbols[0]].exchange.hours
        self._fill_day = exchange.get_next_trading_day(day).date()

    def _closes(self, day: date, month: str) -> list[list[float]]:
        first = logic.add_months(month, -logic.MAX_LOOKBACK)
        start = datetime(int(first[:4]), int(first[5:]), 1)
        month_ends = []
        for symbol in self._symbols:
            bars = self.history[TradeBar](symbol, start, self.time, Resolution.DAILY)
            pairs = [(bar.end_time.strftime("%Y-%m-%d"), float(bar.close)) for bar in bars]
            month_ends.append(logic.month_end_closes(pairs, day.isoformat()))
        return logic.close_matrix(month_ends, self._run.tickers, month)

    def on_order_event(self, order_event: OrderEvent) -> None:
        if order_event.status == OrderStatus.INVALID:
            raise RuntimeError(f"order invalid: {order_event}")
        if order_event.status != OrderStatus.FILLED:
            return
        if self.time.date() != self._fill_day:
            raise RuntimeError(f"fill on {self.time.date()}, expected {self._fill_day}")
        security = self.securities[order_event.symbol]
        if order_event.fill_price != security.open:
            raise RuntimeError(f"fill at {order_event.fill_price}, open was {security.open}")
        fee = float(order_event.order_fee.value.amount)
        expected = logic.fee(order_event.fill_quantity * order_event.fill_price)
        if abs(fee - expected) > 1e-6 * max(1.0, expected):
            raise RuntimeError(f"fee {fee}, expected {expected}")
        self._fees += fee
        self._filled += 1

    def on_end_of_algorithm(self) -> None:
        if not self._months or self._months[-1] != self._run.end:
            last = self._months[-1] if self._months else "none"
            raise RuntimeError(f"no month-end value for {self._run.end}; the last is {last}")
        if self._filled != self._submitted:
            raise RuntimeError(f"{self._submitted} orders submitted, {self._filled} filled")
        messages = logic.format_log(
            self._run, self._months, self._values, self._fees, self._filled, self._min_cash
        )
        for message in messages:
            self.log(message)
