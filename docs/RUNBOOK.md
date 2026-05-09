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
- 按配置筛选 ETF。
- 运行网格做T模拟。
- 写入 `data/local.db`。
- 输出 `reports/signals.csv`、`reports/trades.csv`、`reports/positions.csv`、`reports/daily_summary.csv`、`reports/universe.csv`。
- 输出 `reports/audit_report.csv` 和 `reports/audit_report.md`。

## 2.1 跑一次真实 ETF 日线回测

```powershell
python -m src.app.run_backtest --provider akshare
```

默认会拉取配置里的 5 只 ETF：

```text
510300 沪深300ETF
510500 中证500ETF
159915 创业板ETF
588000 科创50ETF
518880 黄金ETF
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

## 2.2 查看策略审计报告

每次回测后会生成：

```text
reports/audit_report.csv
reports/audit_report.md
```

审计报告用于逐笔核对：

- 信号日和实际成交日是否错开。
- 买入信号是否满足 `price <= reference_price * (1 - grid_pct)`。
- 卖出信号是否满足 `price >= avg_cost * (1 + take_profit_pct)`。
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

- 关闭趋势过滤。
- 当前确认下跌趋势过滤。
- 严格低于长均线过滤。

输出文件：

```text
reports/strategy_comparison.csv
```

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
- K 线、买卖点和净值曲线只显示到当前日期。
- `策略检查` 会展示截至当前日期的信号数、成交数、拒绝原因和最近信号。
- `当天信号` 和 `当天成交` 会分开展示，用于核对信号日和实际成交日。
- `当前回放持仓` 会按当前日期之前的可见成交估算选中 ETF 的持仓、成本和浮盈亏。
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
