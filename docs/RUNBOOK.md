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

## 3. 启动本地 API

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

## 4. 启动前端

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
- `Strategy Check` 会展示截至当前日期的信号数、成交数、拒绝原因和最近交易。
- 这个模式用于检查买卖策略是否在当时信息下合理，避免只看最终收益曲线。

成交时序：

- 策略在 T 日收盘后产生信号。
- 回测在 T+1 日开盘执行信号。
- `signals.csv` 的 `datetime` 是信号日期。
- `trades.csv` 的 `datetime` 是实际模拟成交日期。
- 成交记录的 `reason` 会附带 `signal_date=...`，用于回放时核对信号和成交的先后关系。

## 当前限制

- 现在的行情源是确定性样例数据，用于验证项目结构和闭环。
- 还没有接入 AkShare 实时/历史接口。
- 前端只读展示，不提供真实账户登录或下单能力。
- 前端生产构建已通过 `npm run build` 验证。
