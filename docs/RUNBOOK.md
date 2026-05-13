# Runbook

## 1. 安装 Python 依赖

```powershell
pip install -r requirements.txt
```

## 2. 跑一次样例回测

```powershell
python -m src.app.run_backtest --sample --periods 120
```

这条命令会完成：

- 生成本地样例 ETF 日线。
- 写入 `data/parquet/bars_1d.parquet`。
- 用 DuckDB 读取 Parquet。
- 先用配置里的 `universe.selection_lookback_days` 做初始筛选，之后才开始交易，避免用未来数据选 ETF。
- 运行网格做T模拟。
- 写入 `data/local.db`。
- 输出 `reports/signals.csv`、`reports/trades.csv`、`reports/positions.csv`、`reports/daily_summary.csv`、`reports/universe.csv`。
- 输出 `reports/audit_report.csv` 和 `reports/audit_report.md`。

## 2.1 跑一次真实 ETF 日线回测

```powershell
python -m src.app.run_backtest --provider akshare
```

默认会拉取配置里的扩展 ETF 池：

```text
510050 上证50ETF
510300 沪深300ETF
510500 中证500ETF
159915 创业板ETF
588000 科创50ETF
518880 黄金ETF
512880 证券ETF
512010 医药ETF
159928 消费ETF
159995 芯片ETF
516160 新能源ETF
512660 军工ETF
513100 纳指ETF
513500 标普500ETF
513180 恒生科技ETF
```

也可以指定少量 ETF：

```powershell
python -m src.app.run_backtest --provider akshare --symbols 510300,159915,588000
```

AkShare 数据源说明：

- 优先尝试东方财富 ETF 日线接口。
- 如果东方财富接口因为网络或代理失败，会自动 fallback 到新浪 ETF 日线接口。
- 当前标准化字段仍然是 `symbol, name, datetime, open, high, low, close, volume, amount, source, adjust`。
- `source` 字段会记录实际来源，例如 `akshare_em` 或 `akshare_sina`。
- 回测不会用完整历史区间筛选 ETF；默认先看前 20 个交易日形成标的池，再从下一交易日开始交易。

## 2.2 查看策略审计报告

每次回测后会生成：

```text
reports/audit_report.csv
reports/audit_report.md
```

审计报告用于逐笔核对：

- 信号日和实际成交日是否错开。
- 买入信号是否满足 `price <= reference_price * (1 - grid_pct)`。
- 卖出信号是否满足 `price >= grid_lot_entry * (1 + take_profit_pct)`。
- 信号产生时的现金、持仓、均价、底仓是否合理。
- 次日开盘成交价、滑点、手续费是否被记录。
- 风控拦截原因，例如 `max_symbol_position_pct`、`max_total_position_pct`。
- 策略过滤原因，例如 `buy_cooldown_days`、`max_grid_levels`。

推荐先看 Markdown 汇总，再用 CSV 按 `symbol`、`status`、`reject_reason` 筛选明细。

当前网格策略已启用：

```yaml
strategy:
  max_grid_levels: 5
  buy_cooldown_days: 2
  trend_filter:
    enabled: true
    ma_short: 20
    ma_long: 60
```

这两个参数用于减少下跌阶段连续加仓：

- `max_grid_levels`：限制每只 ETF 的 T 仓最多加几层。
- `buy_cooldown_days`：同一只 ETF 买入后，至少等待几个交易日才允许下一次买入。
- `trend_filter`：当价格低于长均线，且短均线也弱于长均线时，拦截新增网格买入。

## 2.3 对比策略参数

在已经有本地行情 Parquet 后，可以运行：

```powershell
python -m src.app.compare_strategy_params
```

它会对比：

- `buy_hold_max_total_position`：按策略可实际成交的次日开盘等权买入，目标仓位为配置里的 `risk.max_total_position_pct`，之后不操作。
- `buy_hold_full_position`：按策略可实际成交的次日开盘等权尽量满仓买入，之后不操作。
- 关闭趋势过滤。
- 当前确认下跌趋势过滤。
- 严格低于长均线过滤。

买入并持有基准用于判断策略收益来自哪里：

- 如果策略收益低于买入持有，但回撤明显更小，说明策略主要价值是控制波动和仓位风险。
- 如果策略收益高于买入持有，同时回撤也可控，才说明策略真的创造了明显超额收益。
- 如果所有策略都跟买入持有一起上涨，要警惕收益主要来自市场整体上涨。

输出文件：

```text
reports/strategy_comparison.csv
```

## 2.4 训练/验证/测试实验

当需要避免“在同一段历史里调参又评价”的问题时，运行：

```powershell
python -m src.app.run_experiment
```

它会读取配置里的三段时间：

```yaml
experiment:
  train:
    start_date: "2024-01-01"
    end_date: "2024-12-31"
  validation:
    start_date: "2025-01-01"
    end_date: "2025-12-31"
  test:
    start_date: "2026-01-01"
    end_date: "2026-05-08"
```

实验流程：

- 训练期：跑内置策略版本和 `experiment.parameter_grid` 参数组合，按 `收益 - 回撤惩罚` 选出一个训练期最优版本。
- 内置策略版本包括：当前策略、关闭趋势过滤、严格趋势过滤、提高仓位、放慢卖出、上涨趋势少卖、趋势增强底仓、波动率自适应网格。
- 验证期：固定训练期选出的版本，不再重新调参，观察是否还能有效。
- 测试期：作为最后留出区间，用来减少过拟合错觉。
- 每个区间都会重新用初始观察窗口筛选 ETF，避免使用该区间后半段信息。

输出文件：

```text
reports/experiment_comparison.csv
reports/experiment_summary.csv
reports/experiment_walk_forward.csv
reports/experiment_variant_walk_forward.csv
reports/experiment_metrics.csv
reports/experiment_variant_metrics.csv
```

其中 `experiment_summary.csv` 只展示训练期选中策略在各区间的表现，`experiment_comparison.csv` 展示所有策略版本和买入持有基准，`experiment_walk_forward.csv` 保留每轮训练期选中策略后的验证结果，`experiment_variant_walk_forward.csv` 展示每个策略版本跨所有验证窗口的完整表现，`experiment_metrics.csv` 汇总选中策略的 walk-forward 胜率、平均超额、最好/最差窗口和稳定性判断，`experiment_variant_metrics.csv` 按策略版本汇总训练/验证/测试收益和完整滚动验证指标。

如果配置启用了 `experiment.walk_forward`，同一个命令还会执行 walk-forward：

```yaml
experiment:
  walk_forward:
    enabled: true
    start_date: "2024-01-01"
    end_date: "2026-05-08"
    train_months: 6
    validation_months: 3
    step_months: 3
```

默认含义是：每轮使用 6 个月训练，随后 3 个月验证，再向后滚动 3 个月。这个结果比单次训练 / 验证 / 测试更接近真实“未来样本外”检查。

实验结果也会通过 API 提供给前端：

```text
GET http://127.0.0.1:8000/api/experiments/summary
GET http://127.0.0.1:8000/api/experiments/comparison
GET http://127.0.0.1:8000/api/experiments/walk-forward
GET http://127.0.0.1:8000/api/experiments/variant-walk-forward
GET http://127.0.0.1:8000/api/experiments/metrics
GET http://127.0.0.1:8000/api/experiments/variant-metrics
```

前端 `实验对比` 页面会展示固定切分表现、训练期策略排名、策略版本总览和 walk-forward 滚动验证结果。

## 2.5 数据质量检查

在已经有本地行情 Parquet 后，可以运行：

```powershell
python -m src.app.check_data_quality
```

输出文件：

```text
reports/data_quality.csv
reports/data_quality.md
```

检查内容包括每只 ETF 的实际交易日、全市场预期交易日、起止日期、完整度、关键字段缺失、重复日期，以及是否有足够数据参与初始筛选。完整度使用当前缓存中全市场实际出现过的交易日集合计算，不用普通工作日历估算，因此 A 股节假日不会被当成缺口。API：

```text
GET http://127.0.0.1:8000/api/data-quality
```

同样的买入持有基准也会通过 API 提供给前端净值图：

```text
GET http://127.0.0.1:8000/api/benchmarks/equity
```

前端会展示：

- 策略总资产曲线。
- `70%仓位买入持有`：使用 `risk.max_total_position_pct`，更适合和当前策略公平比较。
- `满仓买入持有`：用于观察市场本身从起点到终点涨了多少。

## 2.6 行情状态分段

前端和 API 会按等权 ETF 组合判断市场状态：

```text
GET http://127.0.0.1:8000/api/regimes/summary
```

当前分段规则：

- `上涨`：市场指数在长均线上方，短均线也在长均线上方，且 20 日动量较强。
- `下跌`：市场指数低于长均线，短均线也低于长均线，且 20 日动量较弱。
- `震荡`：不满足明确上涨或下跌。
- `样本不足`：均线或动量窗口还没有足够历史数据。

分段统计会比较：

- 策略在该行情状态下的复合收益。
- 70% 买入持有基准在同一批日期里的复合收益。
- 策略超额收益、回撤和成交次数。

## 2.7 收益差距归因报告

在已经完成一次回测后，可以运行：

```powershell
python -m src.app.analyze_attribution
```

输出文件：

```text
reports/attribution_report.md
reports/attribution_summary.csv
reports/attribution_by_regime.csv
reports/attribution_by_symbol.csv
reports/attribution_sell_opportunities.csv
reports/attribution_rejected_buys.csv
```

这个报告用于回答：

- 策略和 70% 买入持有基准差多少。
- 差距主要来自上涨、震荡还是下跌阶段。
- 策略平均仓位是否明显低于基准。
- 卖出后继续上涨的逐笔粗估机会成本。
- 被趋势过滤、仓位上限、冷却期拦截的买入，如果持有到期末的逐笔粗估机会。
- 交易成本是否足以解释收益差距。

## 3. 运行基础测试

```powershell
python -m pytest -q
```

当前测试重点保护：

- 策略在 T 日生成信号，T+1 日按开盘价模拟成交。
- 买入冷却期 `buy_cooldown_days` 会记录策略拦截。
- 网格层数上限 `max_grid_levels` 会记录策略拦截。

## 4. 启动本地 API

```powershell
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

可用接口：

```text
GET http://127.0.0.1:8000/api/health
GET http://127.0.0.1:8000/api/universe
GET http://127.0.0.1:8000/api/bars?symbol=510300
GET http://127.0.0.1:8000/api/trades
GET http://127.0.0.1:8000/api/positions
GET http://127.0.0.1:8000/api/account/equity
```

`/api/signals` 和 `/api/trades` 会返回审计字段 `audit`，前端用它显示信号价、成交价、持仓变化和拦截原因。

## 5. 启动前端

需要先安装 Node.js 和 npm。本机已使用官方 Node.js LTS zip 配置过：

```text
C:\Users\37478\.local\nodejs\node-v24.15.0-win-x64
```

如果新开的 PowerShell 仍然不能识别 `npm`，可以临时执行：

```powershell
$env:Path = "C:\Users\37478\.local\nodejs\node-v24.15.0-win-x64;$env:Path"
```

```powershell
cd frontend
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

看板包含回放模式：

- 用日期滑杆逐步推进 K 线。
- `总览` 页展示账户总览、基准对比、策略与基准净值曲线、行情状态分段。
- `ETF详情` 页展示单只 ETF 的 K 线、买卖点、拦截信号、当前回放持仓和策略检查。
- K 线、买卖点、净值曲线和统计卡片只显示到当前回放日期。
- `策略检查` 会展示截至当前日期的信号数、成交数、拒绝原因和最近信号。
- `当天信号` 和 `当天成交` 会分开展示，用于核对信号日和实际成交日。
- `当前回放持仓` 会按当前日期之前的可见成交估算选中 ETF 的持仓、成本和浮盈亏。
- `减仓后停止交易对比` 会在单只 ETF 上比较当前策略和“首次卖出后不再交易、只持有剩余仓位”的假设收益。
- 这个模式用于检查买卖策略是否在当时信息下合理，避免只看最终收益曲线。

成交时序：

- 策略在 T 日收盘后产生信号。
- 回测在 T+1 日开盘执行信号。
- `signals.csv` 的 `datetime` 是信号日期。
- `trades.csv` 的 `datetime` 是实际模拟成交日期。
- 成交记录的 `reason` 会附带 `signal_date=...`，用于回放时核对信号和成交的先后关系。

## 当前限制

- 当前默认行情源是 AkShare 历史日线；样例数据仍可用来做离线验证。
- 现在仍是日线级别回测，还不是分钟级或实时交易系统。
- 前端只读展示，不提供真实账户登录或下单能力。
- 前端生产构建已通过 `npm run build` 验证。
