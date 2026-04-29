# Frontend Dashboard

本目录用于本地只读看板。

第一版目标：

- 展示 ETF 观察列表。
- 展示 K 线和成交量。
- 在 K 线上标记模拟买入、卖出和风控拦截点。
- 展示虚拟账户、持仓、交易日志、净值和回撤。

技术选择：

```text
React + Vite
TradingView Lightweight Charts
ECharts
```

前端只读取本地 FastAPI 接口，不接真实券商账户，不提供实盘下单能力。
