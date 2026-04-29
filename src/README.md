# Source Layout

```text
data/          AkShare 数据抓取和字段标准化
storage/       Parquet、DuckDB、SQLite 读写
universe/      ETF 自动筛选
strategy/      网格做T、均值回归等策略
broker_sim/    虚拟账户、订单、成交和撮合
risk/          仓位、现金、底仓、交易频率等风控
reporting/     CSV、HTML、图表数据输出
api/           FastAPI 本地接口
app/           命令行入口和任务调度入口
```

第一版优先实现 `data -> storage -> universe -> strategy -> broker_sim -> reporting`，再接 `api` 和 `frontend`。
