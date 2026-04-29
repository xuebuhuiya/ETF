# Tech Stack

## 第一版推荐组合

```text
后端：Python + FastAPI
行情缓存：Parquet
本地查询：DuckDB
交易状态：SQLite
前端：React + Vite
K线图：TradingView Lightweight Charts
统计图：ECharts
```

这套组合的目标是：本地部署简单、回测查询方便、前端可以快速展示 K 线和交易结果。

## 为什么先不用 MongoDB

MongoDB 可以用，但不是第一版的默认选择。

原因：

- ETF 行情是标准时间序列表，字段固定，适合 Parquet 和 DuckDB。
- 交易、信号、持仓、账户快照是结构化关系数据，适合 SQLite。
- MongoDB 需要单独安装和运行服务，会增加本地部署复杂度。
- 第一版更重要的是跑通策略、风控、回测和展示，不需要复杂文档数据库。

适合以后引入 MongoDB 的场景：

- 保存大量策略运行事件。
- 保存复杂 JSON 格式的盘口快照。
- 保存非结构化日志、告警、调试上下文。
- 多策略并行运行，需要更灵活的事件查询。

## 存储分工

```text
data/parquet/bars_1d/       ETF 日线
data/parquet/bars_1m/       ETF 分钟线
data/parquet/spot/          ETF 实时快照
data/local.db               SQLite 状态库
reports/                    CSV/HTML 报告
```

SQLite 建议表：

```text
strategy_runs
signals
orders
trades
positions
account_snapshots
universe_snapshots
```

Parquet 建议字段：

```text
symbol
name
datetime
open
high
low
close
volume
amount
source
adjust
```

## 前端展示

第一版前端只做本地只读看板。

页面：

- ETF 观察列表。
- K 线与成交量。
- 买入、卖出、风控拦截标记。
- 当前虚拟账户。
- 当前持仓。
- 交易日志。
- 净值和回撤曲线。

图表：

- K 线：TradingView Lightweight Charts。
- 收益、回撤、分组统计：ECharts。

## 后续性能路线

先用 Python 把策略和数据闭环跑通。

如果以后真的出现性能瓶颈，再逐步升级：

```text
Python 策略与调度
  -> DuckDB/Parquet 批量查询优化
  -> 后台任务和缓存优化
  -> 撮合/风控热点改 C++ 或 Rust
  -> 更专业的行情源和事件存储
```

不要一开始就为了可能的高频场景重写成 C++。第一版最重要的是验证规则和数据闭环。
