# ETF T+0 Simulation Lab

本项目用于构建一个本地 ETF 做T模拟系统：自动筛选 ETF，使用假设本金运行规则化策略，只记录虚拟交易、持仓、收益和风险指标，并通过本地数据库和前端看板展示 K 线、信号、交易和账户状态。不连接真实券商账户，不自动实盘下单。

## 目标

- 使用 AkShare 获取 A 股 ETF 实时、历史和分钟级行情。
- 按流动性、波动率、价格区间、趋势和成交额自动筛选 ETF。
- 用虚拟本金创建本地模拟账户，执行规则化做T策略。
- 记录每次触发原因、模拟成交、手续费、滑点、持仓、现金和收益。
- 使用本地数据库保存行情缓存、模拟交易、信号、持仓和账户快照。
- 提供本地网页看板，展示 ETF K 线、成交量、交易标记、收益曲线和回撤。
- 输出每日/阶段性报告，验证策略是否稳定、是否过度交易、是否有回撤风险。

## 当前技术路线

第一版采用轻量本地架构：

```text
数据源：AkShare
后端：Python + FastAPI
行情存储：Parquet + DuckDB
交易状态：SQLite
前端：React + Vite
K线图：TradingView Lightweight Charts
统计图：ECharts
```

MongoDB 暂不作为第一版默认数据库。它适合复杂 JSON 事件、策略日志和后续更大的实时数据流，但第一版的 ETF OHLCV 行情和交易表更适合用 SQLite、DuckDB 和 Parquet，部署更简单，也更方便回测和聚合查询。

## 推荐借鉴项目

| 项目 | 用途 | 借鉴点 |
| --- | --- | --- |
| AkShare | 数据源 | ETF 实时行情、历史行情、分钟数据 |
| xalpha | 基金/ETF账户逻辑 | 网格、定投、基金账户、收益记录 |
| qteasy | 本地量化框架 | 本地数据、回测、模拟交易、交易成本、T+1规则 |
| RQAlpha | 回测架构 | 撮合、账户、风控、报告模块划分 |
| backtesting.py / vectorbt | 快速验证 | 指标计算、参数扫描、绩效统计 |

## 第一版范围

第一版只做本地模拟：

- 不登录证券账户。
- 不保存账号、密码、验证码、身份证等敏感信息。
- 不自动下真实订单。
- 只输出模拟交易和操作提醒。
- 本地看板只读展示，不提供真实交易入口。

## 项目结构

```text
ETF/
  README.md
  config/
    config.example.yaml
  docs/
    ARCHITECTURE.md
    ROADMAP.md
    RUNBOOK.md
    STRATEGY_SPEC.md
    TECH_STACK.md
  src/
    data/          # ETF行情与缓存
    storage/       # SQLite/DuckDB/Parquet 读写
    universe/      # ETF筛选
    strategy/      # 做T规则
    broker_sim/    # 虚拟账户与撮合
    risk/          # 风控
    reporting/     # 报告与图表
    api/           # FastAPI 本地接口
    app/           # 命令行入口
  frontend/        # React + Vite 本地看板
  data/            # 本地行情缓存，不提交敏感数据
    cache/         # 原始缓存
    parquet/       # OHLCV 行情
    local.db       # SQLite 本地状态库，不提交
  reports/         # 回测和模拟报告
```

## 核心流程

```text
拉取ETF池
  -> 清洗行情数据
  -> 写入 Parquet / DuckDB 可查询缓存
  -> 按规则筛选候选ETF
  -> 初始化虚拟账户
  -> 逐个行情tick/分钟bar运行策略
  -> 生成虚拟订单
  -> 模拟撮合成交
  -> 更新现金、持仓、盈亏
  -> 风控检查
  -> 写入 SQLite 状态库和 CSV 报告
  -> FastAPI 提供本地接口
  -> 前端展示 K 线、交易标记和账户曲线
```

## 建议第一版默认参数

```text
初始本金：100000 CNY
单只ETF最大仓位：20%
总仓位上限：70%
底仓比例：50%
单次做T金额：5000-10000 CNY
手续费：万分之0.5到万分之3，可配置
滑点：0.01%到0.05%，可配置
交易单位：100份
最小成交金额：1000 CNY
```

## 输出结果

- `reports/daily_summary.csv`：每日账户净值、现金、持仓、市值、收益、回撤。
- `reports/trades.csv`：每笔模拟交易的时间、ETF、方向、数量、价格、原因。
- `reports/positions.csv`：当前虚拟持仓。
- `reports/signals.csv`：触发过但未成交/被风控拦截的信号。
- `reports/audit_report.csv`：逐笔策略审计明细。
- `reports/audit_report.md`：策略审计摘要。
- `reports/report.html`：可视化报告，后续实现。
- `data/parquet/*.parquet`：ETF 日线、分钟线和实时快照缓存。
- `data/local.db`：模拟交易、信号、持仓、账户快照和筛选结果。

## 下一步

先实现一个最小闭环：

1. 用 AkShare 拉取 ETF 实时行情和历史日线。
2. 选出成交额靠前、波动率合适的 ETF。
3. 用一个简单网格/均值回归做T规则跑历史模拟。
4. 把行情写入 Parquet，把交易状态写入 SQLite。
5. 输出交易日志和收益统计。
6. 用 FastAPI + React 做一个本地 K 线看板。

当前已支持两种数据模式：

```powershell
python -m src.app.run_backtest --sample --periods 120
python -m src.app.run_backtest --provider akshare
```

## 运行方式

详见 [RUNBOOK.md](docs/RUNBOOK.md)。
