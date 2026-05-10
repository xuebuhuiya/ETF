"""AkShare ETF market data adapter."""

from __future__ import annotations

from dataclasses import dataclass

import akshare as ak
import pandas as pd


DEFAULT_ETFS = {
    "510050": "上证50ETF",
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "159915": "创业板ETF",
    "588000": "科创50ETF",
    "518880": "黄金ETF",
    "512880": "证券ETF",
    "512010": "医药ETF",
    "159928": "消费ETF",
    "159995": "芯片ETF",
    "516160": "新能源ETF",
    "512660": "军工ETF",
    "513100": "纳指ETF",
    "513500": "标普500ETF",
    "513180": "恒生科技ETF",
}


@dataclass(frozen=True)
class ETFRequest:
    symbol: str
    name: str


def parse_symbol_list(symbols: str | None) -> list[ETFRequest]:
    """Parse CLI symbols like 510300,159915 or 510300:沪深300ETF."""

    if not symbols:
        return [ETFRequest(symbol=symbol, name=name) for symbol, name in DEFAULT_ETFS.items()]

    requests: list[ETFRequest] = []
    for item in symbols.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            symbol, name = item.split(":", 1)
            requests.append(ETFRequest(symbol=symbol.strip(), name=name.strip()))
        else:
            requests.append(ETFRequest(symbol=item, name=DEFAULT_ETFS.get(item, item)))
    return requests


def fetch_etf_daily_bars(
    requests: list[ETFRequest],
    *,
    start_date: str,
    end_date: str,
    adjust: str = "",
) -> pd.DataFrame:
    """Fetch ETF daily bars from AkShare and normalize columns."""

    frames: list[pd.DataFrame] = []
    for request in requests:
        raw = _fetch_em_daily(request, start_date=start_date, end_date=end_date, adjust=adjust)
        source = "akshare_em"
        if raw.empty:
            raw = _fetch_sina_daily(request, start_date=start_date, end_date=end_date)
            source = "akshare_sina"
        if raw.empty:
            continue

        frame = raw.rename(
            columns={
                "日期": "datetime",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }
        )
        frame = frame[["datetime", "open", "high", "low", "close", "volume", "amount"]].copy()
        frame.insert(0, "name", request.name)
        frame.insert(0, "symbol", request.symbol)
        frame["datetime"] = pd.to_datetime(frame["datetime"]).dt.strftime("%Y-%m-%d")
        frame["source"] = source
        frame["adjust"] = adjust or "none"
        frames.append(frame)

    if not frames:
        return pd.DataFrame(
            columns=[
                "symbol",
                "name",
                "datetime",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "source",
                "adjust",
            ]
        )

    bars = pd.concat(frames, ignore_index=True)
    return bars.sort_values(["symbol", "datetime"]).reset_index(drop=True)


def _compact_date(value: str) -> str:
    return value.replace("-", "")


def _fetch_em_daily(request: ETFRequest, *, start_date: str, end_date: str, adjust: str) -> pd.DataFrame:
    try:
        return ak.fund_etf_hist_em(
            symbol=request.symbol,
            period="daily",
            start_date=_compact_date(start_date),
            end_date=_compact_date(end_date),
            adjust=adjust,
        )
    except Exception:
        return pd.DataFrame()


def _fetch_sina_daily(request: ETFRequest, *, start_date: str, end_date: str) -> pd.DataFrame:
    sina_symbol = _sina_symbol(request.symbol)
    try:
        raw = ak.fund_etf_hist_sina(symbol=sina_symbol)
    except Exception:
        return pd.DataFrame()

    if raw.empty:
        return raw

    frame = raw.rename(columns={"date": "日期"})
    frame = frame.rename(
        columns={
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "amount": "成交额",
        }
    )
    frame["日期"] = pd.to_datetime(frame["日期"])
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    frame = frame[(frame["日期"] >= start) & (frame["日期"] <= end)].copy()
    frame["日期"] = frame["日期"].dt.strftime("%Y-%m-%d")
    return frame


def _sina_symbol(symbol: str) -> str:
    if symbol.startswith(("15", "16", "18")):
        return f"sz{symbol}"
    return f"sh{symbol}"
