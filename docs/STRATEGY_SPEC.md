# Strategy Spec

## 策略目标

做T策略不是预测长期方向，而是在已有或虚拟底仓基础上，利用 ETF 日内/短期波动降低持仓成本或验证规则有效性。

第一版只验证规则，不追求最复杂。

## 策略实验原则

策略参数不能只在同一段历史里反复调到最好看。当前项目把实验分成三段：

- 训练期：用来比较策略版本、选择参数。
- 验证期：固定训练期选出的参数，检查是否仍然有效。
- 测试期：最后留出，尽量减少过拟合。

策略规则本身仍放在 `src/strategy/`，训练、验证、参数搜索和策略版本对比放在 `src/experiment/`。

## ETF 筛选规则

默认筛选流程：

1. 获取全市场 ETF 实时行情。
2. 按成交额排序，保留前 100。
3. 过滤价格小于 0.5 的 ETF。
4. 计算近 20 日波动率。
5. 保留波动率适中的 ETF。
6. 每天最多选择 5 到 10 只进入模拟池。

默认参数：

```yaml
universe:
  selection_lookback_days: 20
  max_candidates: 10
  min_price: 0.5
  min_avg_amount_20d: 50000000
  min_volatility_20d: 0.008
  max_volatility_20d: 0.04
```

回测时只用初始观察窗口筛选 ETF，默认用前 20 个交易日形成标的池，之后才开始产生交易信号。这样可以避免用 2026 年的数据反过来决定 2024 年买什么。

## 网格做T规则

适合震荡 ETF。

核心逻辑：

- 以参考价为中心建立网格。
- 每跌一格买入一份 T 仓。
- 每涨一格卖出一份 T 仓。
- 保留底仓，不卖穿。

示例：

```yaml
strategy:
  name: grid_t
  grid_pct: 0.006
  take_profit_pct: 0.006
  max_grid_levels: 5
  buy_cooldown_days: 2
  base_position_pct: 0.5
  trade_amount: 8000
```

买入触发：

```text
当前价 <= 最近参考价 * (1 - grid_pct)
当前网格层数 < max_grid_levels
距离上次买入不少于 buy_cooldown_days 个交易日
现金充足
当前ETF仓位未超过单只上限
当天买入次数未超过限制
```

卖出触发：

```text
当前价 >= 对应网格加仓批次成本 * (1 + take_profit_pct)
可卖份额充足
卖出后仍保留底仓
当天卖出次数未超过限制
```

## 均值回归做T规则

适合波动但未明显单边趋势的 ETF。

指标：

- MA20。
- 偏离率：`close / ma20 - 1`。

买入触发：

```text
偏离率 <= -1.2%
近20日波动率在允许范围内
现金充足
```

卖出触发：

```text
偏离率 >= 0.8%
可卖份额充足
不低于底仓
```

## 风控规则

```yaml
risk:
  max_total_position_pct: 0.7
  max_symbol_position_pct: 0.2
  min_cash_pct: 0.1
  max_trades_per_symbol_per_day: 4
  max_trades_per_day: 20
  max_daily_loss_pct: 0.02
  pause_after_consecutive_losses: 3
```

## 交易成本

第一版使用简化模型：

```text
成交价 = 信号价 * (1 + 滑点方向)
手续费 = 成交金额 * fee_rate
买入占用现金 = 成交金额 + 手续费
卖出增加现金 = 成交金额 - 手续费
```

风控检查使用包含滑点后的预计成交价，而不是原始信号价或开盘价。

注意：

- A 股 ETF 通常无印花税，但不同券商佣金不同。
- 第一版手续费可配置，不默认代表真实券商费率。

## 日志字段

`signals.csv`：

```text
datetime,symbol,name,side,price,quantity,strategy,reason,status,reject_reason
```

`trades.csv`：

```text
datetime,symbol,name,side,price,quantity,amount,fee,slippage,pnl,reason
```

`daily_summary.csv`：

```text
date,cash,market_value,total_equity,daily_pnl,total_return,max_drawdown,trade_count
```
