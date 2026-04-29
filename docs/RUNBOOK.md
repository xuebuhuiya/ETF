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

需要先安装 Node.js 和 npm。

```powershell
cd frontend
npm install
npm run dev
```

默认前端地址：

```text
http://127.0.0.1:5173
```

## 当前限制

- 现在的行情源是确定性样例数据，用于验证项目结构和闭环。
- 还没有接入 AkShare 实时/历史接口。
- 前端只读展示，不提供真实账户登录或下单能力。
- 本地机器当前没有可用 `npm`，所以前端构建需要等 Node.js/npm 配好后再验证。
