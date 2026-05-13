# ETF T+0 Simulation Lab

这是一个本地 ETF 做 T / 网格策略模拟系统。项目用于研究规则化 ETF 策略，不连接真实券商账户，不自动下单，只做本地数据、虚拟交易、回测、审计、归因和前端展示。

当前项目已经从最初的骨架推进到一个可运行的小型研究系统：可以拉取或读取 ETF 日线数据，筛选标的池，运行网格策略，和买入持有基准比较，生成审计与归因报告，并用训练 / 验证 / 测试切分检查策略是否可能泛化。

## 当前状态

已完成：

- AkShare / 本地 Parquet / 样例数据三种数据模式。
- ETF 标的筛选，默认使用初始观察窗口，避免用未来数据选标的。
- 网格做 T 策略，支持底仓、网格加仓、分层卖出、冷却期、最大网格层数、趋势过滤。
- 虚拟账户、手续费、滑点、T+1 开盘成交、仓位风控。
- SQLite 保存信号、交易、持仓、账户快照和标的池。
- CSV / Markdown 报告，包括交易、审计、收益差距归因。
- FastAPI 本地只读接口。
- React + Vite 前端看板，展示账户总览、ETF K 线、交易标记、回放和基准曲线。
- 买入持有基准，包括 70% 仓位和满仓基准。
- 行情状态分段：上涨、震荡、下跌、样本不足。
- 训练 / 验证 / 测试实验框架，用于策略版本和参数网格对比。
- Walk-forward 滚动验证，用多轮训练窗口和未来验证窗口检查样本外表现。
- 基础测试覆盖核心回测、基准、归因和实验模块。

最近一次完整实验显示：训练期选中的版本是 `no_trend_filter`。它在训练期和验证期仍跑输 70% 买入持有，但在测试期小幅跑赢。当前策略还不能证明有稳定超额收益，更像一个低回撤、低仓位、偏震荡的策略原型。

## 技术栈

```text
数据源：AkShare / 本地样例数据
后端：Python + FastAPI
行情存储：Parquet + DuckDB
交易状态：SQLite
前端：React + Vite
K线图：TradingView Lightweight Charts
统计图：ECharts
测试：pytest
```

MongoDB 暂不作为默认数据库。当前阶段的 OHLCV 行情、交易表和账户快照更适合用 Parquet、DuckDB 和 SQLite，部署简单，也方便回测和聚合分析。

## 项目结构

```text
ETF/
  config/
    config.example.yaml      # 本地配置、策略参数、实验区间
  docs/
    RUNBOOK.md               # 运行手册
    STRATEGY_SPEC.md         # 策略规则说明
    ARCHITECTURE.md          # 架构说明
    ROADMAP.md               # 路线图
    TECH_STACK.md            # 技术选型
  src/
    data/                    # ETF 数据获取与样例数据
    storage/                 # SQLite / DuckDB / Parquet 读写
    universe/                # ETF 标的筛选
    strategy/                # 做 T 策略规则
    broker_sim/              # 虚拟账户、撮合、风控
    analysis/                # 基准、行情状态、分析工具
    reporting/               # CSV / Markdown 报告
    experiment/              # 训练、验证、测试和参数实验
    api/                     # FastAPI 本地接口
    app/                     # 命令行入口
  frontend/                  # React + Vite 本地看板
  data/                      # 本地行情和 SQLite 状态库
  reports/                   # 回测、审计、归因和实验输出
  tests/                     # 自动化测试
```

## 核心流程

```text
获取或读取 ETF 日线
  -> 写入 / 读取 Parquet
  -> 初始观察窗口筛选 ETF
  -> 从筛选日之后开始回测
  -> 策略在 T 日生成信号
  -> T+1 日开盘按滑点和手续费模拟成交
  -> 风控检查现金、单标的仓位、总仓位、底仓保护
  -> 更新现金、持仓、收益和回撤
  -> 写入 SQLite 和 CSV 报告
  -> FastAPI 提供本地接口
  -> 前端展示净值、K 线、交易、回放和基准对比
```

## 常用命令

安装 Python 依赖：

```powershell
pip install -r requirements.txt
```

跑样例数据：

```powershell
python -m src.app.run_backtest --sample --periods 120
```

跑本地已缓存 ETF 数据：

```powershell
python -m src.app.run_backtest --provider local
```

用 AkShare 拉取真实 ETF 日线并回测：

```powershell
python -m src.app.run_backtest --provider akshare
```

对比策略参数和买入持有基准：

```powershell
python -m src.app.compare_strategy_params
```

生成收益差距归因报告：

```powershell
python -m src.app.analyze_attribution
```

运行训练 / 验证 / 测试实验：

```powershell
python -m src.app.run_experiment
```

运行测试：

```powershell
python -m pytest -q
```

启动后端：

```powershell
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

访问：

```text
http://127.0.0.1:5173/
```

## 主要输出

普通回测输出：

```text
reports/daily_summary.csv
reports/signals.csv
reports/trades.csv
reports/positions.csv
reports/universe.csv
reports/audit_report.csv
reports/audit_report.md
```

策略对比输出：

```text
reports/strategy_comparison.csv
```

归因分析输出：

```text
reports/attribution_report.md
reports/attribution_summary.csv
reports/attribution_by_regime.csv
reports/attribution_by_symbol.csv
reports/attribution_sell_opportunities.csv
reports/attribution_rejected_buys.csv
```

实验框架输出：

```text
reports/experiment_comparison.csv
reports/experiment_summary.csv
reports/experiment_walk_forward.csv
reports/experiment_variant_walk_forward.csv
reports/experiment_metrics.csv
reports/experiment_variant_metrics.csv
```

数据质量输出：

```text
reports/data_quality.csv
reports/data_quality.md
```

## 关键设计修正

项目已经修复了几个会影响回测可信度的问题：

- 标的池筛选不使用完整未来区间，只使用初始观察窗口。
- 买入持有基准的入场时间和策略的 T+1 开盘成交口径对齐。
- 风控检查使用含滑点的预计成交价。
- 网格卖出按每一笔加仓批次成本触发，而不是整体平均成本。
- 动态网格卖出成交后，按信号生成时的实际止盈阈值消耗加仓批次。
- 归因报告中的被拒买入机会使用去重保守估计，同时保留逐笔上限，避免误读。
- 训练、验证、测试区间分离，减少同一段历史里调参又评价导致的过拟合。
- 实验指标增加 walk-forward 胜率、平均超额、最好/最差窗口、收益/回撤比和策略版本总览；策略版本指标会跨所有验证窗口评价，不只统计被训练期选中的窗口。
- 数据质量完整度基于缓存里的全市场实际交易日集合计算，避免把 A 股节假日误判为缺口。

## 当前策略结论

当前网格策略已经能在本地完整运行，但还不是一个可以认为“稳定优于买入持有”的策略。

目前观察到的问题：

- 策略平均仓位偏低，上涨阶段容易跑输买入持有。
- 趋势过滤会拦截大量买入，降低下跌风险，也可能错过反弹。
- 分层卖出更符合网格逻辑，但上涨行情中仍可能过早减仓。
- 已经加入上涨趋势少卖、趋势增强底仓、波动率自适应网格等实验策略版本，但仍需要更多样本验证。
- 参数网格还很小，需要继续扩展实验维度。

下一步更适合做：

- 继续扩大参数网格，特别是仓位、止盈倍率、波动率窗口和趋势判断参数。
- 增加更强的趋势持仓增强或动态仓位策略。
- 用 walk-forward 和数据质量报告作为每次策略迭代前后的固定检查。

## 说明

本项目只用于策略研究和本地模拟，不构成投资建议，也不会连接真实券商账户或自动实盘交易。

更详细的运行步骤见 [docs/RUNBOOK.md](docs/RUNBOOK.md)。
