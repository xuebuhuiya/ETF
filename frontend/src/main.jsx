import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { createChart, createSeriesMarkers, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import * as echarts from 'echarts';
import './styles.css';

const API_BASE = 'http://127.0.0.1:8000';
const STATUS_LABELS = {
  filled: '已成交',
  rejected: '已拦截',
  pending: '待成交',
};
const SIDE_LABELS = {
  buy: '买入',
  sell: '卖出',
};
const REJECT_REASON_LABELS = {
  max_symbol_position_pct: '单只 ETF 仓位上限',
  max_total_position_pct: '总仓位上限',
  min_cash_pct: '现金保留不足',
  insufficient_cash: '现金不足',
  max_trades_per_day: '单日成交次数上限',
  max_trades_per_symbol_per_day: '单只 ETF 单日成交次数上限',
  base_position_protected: '底仓保护',
  buy_cooldown_days: '买入冷却期',
  max_grid_levels: '网格层数上限',
  trend_filter: '趋势过滤',
  quantity_not_lot_sized: '份额不足一手',
};
const BENCHMARK_LABELS = {
  buy_hold_max_total_position: '70%仓位买入持有',
  buy_hold_full_position: '满仓买入持有',
};
const REGIME_LABELS = {
  uptrend: '上涨',
  range: '震荡',
  downtrend: '下跌',
  not_ready: '样本不足',
};

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || value === '') return '-';
  return Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '-';
}

function formatPct(value) {
  if (value === null || value === undefined || value === '') return '-';
  return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : '-';
}

function sideLabel(side) {
  return SIDE_LABELS[side] ?? side;
}

function rejectLabel(reason) {
  return REJECT_REASON_LABELS[reason] ?? reason ?? '-';
}

function valueClass(value) {
  if (value === null || value === undefined || value === '') return '';
  return Number(value) >= 0 ? 'positive' : 'negative';
}

function cleanReason(reason) {
  if (!reason) return '-';
  if (reason.includes('initialize_base_position')) return '建立底仓';
  if (reason.includes('grid_buy')) return '网格买入触发';
  if (reason.includes('grid_sell')) return '止盈卖出触发';
  return reason;
}

function sameDate(row, dateKey = 'datetime', currentDate = '') {
  return dateKeyOf(row[dateKey]) === dateKeyOf(currentDate);
}

function dateKeyOf(value) {
  return String(value ?? '').slice(0, 10);
}

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function KlineChart({ bars, trades, signals }) {
  useEffect(() => {
    let chart;
    const element = document.getElementById('kline-chart');
    element.innerHTML = '';

    if (bars.length === 0) {
      return undefined;
    }

    chart = createChart(element, {
      height: 420,
      layout: { background: { color: '#ffffff' }, textColor: '#1f2937' },
      grid: { vertLines: { color: '#eef2f7' }, horzLines: { color: '#eef2f7' } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    });

    const candleSeries = chart.addSeries(CandlestickSeries);
    candleSeries.setData(
      bars.map((bar) => ({
        time: bar.datetime,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );
    createSeriesMarkers(
      candleSeries,
      [
        ...trades.map((trade) => ({
          time: trade.datetime,
          position: trade.side === 'buy' ? 'belowBar' : 'aboveBar',
          color: trade.side === 'buy' ? '#16a34a' : '#dc2626',
          shape: trade.side === 'buy' ? 'arrowUp' : 'arrowDown',
          text: `${sideLabel(trade.side)} ${trade.quantity}`,
        })),
        ...signals
          .filter((signal) => signal.status === 'rejected')
          .map((signal) => ({
            time: signal.datetime,
            position: signal.side === 'buy' ? 'belowBar' : 'aboveBar',
            color: '#f59e0b',
            shape: 'circle',
            text: `拦截 ${rejectLabel(signal.reject_reason)}`,
          })),
      ],
    );

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    volumeSeries.setData(
      bars.map((bar) => ({
        time: bar.datetime,
        value: bar.volume,
        color: bar.close >= bar.open ? '#86efac' : '#fca5a5',
      })),
    );
    chart.timeScale().fitContent();

    return () => {
      if (chart) chart.remove();
    };
  }, [bars, trades, signals]);

  return <div id="kline-chart" className="chart" />;
}

function EquityChart({ rows, benchmarks }) {
  useEffect(() => {
    let chart;
    const element = document.getElementById('equity-chart');
    if (rows.length === 0) {
      element.innerHTML = '';
      return undefined;
    }

    chart = echarts.init(element);
    const benchmarkVariants = [...new Set(benchmarks.map((row) => row.variant))];
    const benchmarkByVariant = Object.fromEntries(
      benchmarkVariants.map((variant) => [
        variant,
        Object.fromEntries(
          benchmarks
            .filter((row) => row.variant === variant)
            .map((row) => [dateKeyOf(row.date), row.total_equity]),
        ),
      ]),
    );

    chart.setOption({
      legend: { top: 0 },
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 24, top: 36, bottom: 36 },
      xAxis: { type: 'category', data: rows.map((row) => row.date) },
      yAxis: { type: 'value', scale: true },
      series: [
        {
          name: '总资产',
          type: 'line',
          smooth: true,
          data: rows.map((row) => row.total_equity),
          lineStyle: { color: '#2563eb' },
          areaStyle: { color: 'rgba(37, 99, 235, 0.12)' },
        },
        ...benchmarkVariants.map((variant, index) => ({
          name: BENCHMARK_LABELS[variant] ?? variant,
          type: 'line',
          smooth: true,
          showSymbol: false,
          data: rows.map((row) => benchmarkByVariant[variant][dateKeyOf(row.date)] ?? null),
          lineStyle: {
            color: index === 0 ? '#f59e0b' : '#64748b',
            type: index === 0 ? 'solid' : 'dashed',
            width: 2,
          },
        })),
      ],
    });

    return () => {
      if (chart) chart.dispose();
    };
  }, [rows, benchmarks]);

  return <div id="equity-chart" className="chart small" />;
}

function BenchmarkOverview({ currentSnapshot, currentBenchmarks }) {
  const fair = currentBenchmarks.find((row) => row.variant === 'buy_hold_max_total_position');
  const full = currentBenchmarks.find((row) => row.variant === 'buy_hold_full_position');
  const fairExcess = currentSnapshot && fair ? currentSnapshot.total_return - fair.total_return : null;

  return (
    <section>
      <h3>基准对比</h3>
      <div className="metrics benchmark">
        <div>
          <span>策略累计收益</span>
          <strong>{formatPct(currentSnapshot?.total_return)}</strong>
        </div>
        <div>
          <span>70%仓位买入持有</span>
          <strong>{formatPct(fair?.total_return)}</strong>
        </div>
        <div>
          <span>满仓买入持有</span>
          <strong>{formatPct(full?.total_return)}</strong>
        </div>
        <div>
          <span>策略相对70%基准</span>
          <strong className={valueClass(fairExcess)}>{formatPct(fairExcess)}</strong>
        </div>
      </div>
    </section>
  );
}

function ScenarioComparison({ currentBar, visibleTrades }) {
  const scenario = useMemo(() => buildReduceThenHoldScenario(visibleTrades, currentBar), [visibleTrades, currentBar]);

  return (
    <section>
      <h3>减仓后停止交易对比</h3>
      <div className="metrics scenario">
        <div>
          <span>当前策略ETF盈亏</span>
          <strong className={valueClass(scenario.current.pnl)}>
            {formatNumber(scenario.current.pnl)}
          </strong>
        </div>
        <div>
          <span>当前策略收益率</span>
          <strong className={valueClass(scenario.current.returnPct)}>
            {formatPct(scenario.current.returnPct)}
          </strong>
        </div>
        <div>
          <span>首次减仓后不动盈亏</span>
          <strong className={valueClass(scenario.holdAfterFirstSell.pnl)}>
            {formatNumber(scenario.holdAfterFirstSell.pnl)}
          </strong>
        </div>
        <div>
          <span>首次减仓后不动收益率</span>
          <strong className={valueClass(scenario.holdAfterFirstSell.returnPct)}>
            {formatPct(scenario.holdAfterFirstSell.returnPct)}
          </strong>
        </div>
        <div>
          <span>首次减仓日期</span>
          <strong>{scenario.firstSellDate ?? '-'}</strong>
        </div>
        <div>
          <span>假设相对当前策略</span>
          <strong className={valueClass(scenario.diff)}>{formatNumber(scenario.diff)}</strong>
        </div>
      </div>
    </section>
  );
}

function buildReduceThenHoldScenario(trades, currentBar) {
  const close = Number(currentBar?.close);
  const empty = {
    firstSellDate: null,
    diff: null,
    current: { pnl: null, returnPct: null },
    holdAfterFirstSell: { pnl: null, returnPct: null },
  };
  if (!Number.isFinite(close) || trades.length === 0) return empty;

  const current = evaluateTradePath(trades, close);
  const firstSellIndex = trades.findIndex((trade) => trade.side === 'sell');
  if (firstSellIndex < 0) {
    return {
      ...empty,
      current,
      diff: null,
    };
  }

  const holdTrades = trades.slice(0, firstSellIndex + 1);
  const holdAfterFirstSell = evaluateTradePath(holdTrades, close);
  return {
    firstSellDate: trades[firstSellIndex].datetime,
    current,
    holdAfterFirstSell,
    diff:
      Number.isFinite(Number(holdAfterFirstSell.pnl)) && Number.isFinite(Number(current.pnl))
        ? holdAfterFirstSell.pnl - current.pnl
        : null,
  };
}

function evaluateTradePath(trades, close) {
  let quantity = 0;
  let cashFlow = 0;
  let invested = 0;

  for (const trade of trades) {
    const amount = Number(trade.amount) || 0;
    const fee = Number(trade.fee) || 0;
    const tradeQuantity = Number(trade.quantity) || 0;
    if (trade.side === 'buy') {
      quantity += tradeQuantity;
      cashFlow -= amount + fee;
      invested += amount + fee;
    } else {
      quantity -= tradeQuantity;
      cashFlow += amount - fee;
    }
  }

  const pnl = cashFlow + quantity * close;
  return {
    pnl,
    returnPct: invested > 0 ? pnl / invested : null,
    quantity,
  };
}

function PlaybackControls({ dates, index, playing, onIndexChange, onPlayingChange }) {
  const currentDate = dates[index] ?? '';
  return (
    <div className="playback">
      <button onClick={() => onPlayingChange(!playing)} disabled={dates.length === 0}>
        {playing ? '暂停' : '播放'}
      </button>
      <button onClick={() => onIndexChange(Math.max(0, index - 1))} disabled={index <= 0}>
        上一天
      </button>
      <input
        type="range"
        min="0"
        max={Math.max(0, dates.length - 1)}
        value={index}
        onChange={(event) => onIndexChange(Number(event.target.value))}
      />
      <button
        onClick={() => onIndexChange(Math.min(dates.length - 1, index + 1))}
        disabled={index >= dates.length - 1}
      >
        下一天
      </button>
      <strong>{currentDate}</strong>
      <span>{dates.length ? `${index + 1}/${dates.length}` : '0/0'}</span>
    </div>
  );
}

function AccountOverview({ currentSnapshot }) {
  return (
    <section>
      <h3>账户总览</h3>
      <div className="metrics account">
        <div>
          <span>现金</span>
          <strong>{formatNumber(currentSnapshot?.cash)}</strong>
        </div>
        <div>
          <span>持仓市值</span>
          <strong>{formatNumber(currentSnapshot?.market_value)}</strong>
        </div>
        <div>
          <span>总资产</span>
          <strong>{formatNumber(currentSnapshot?.total_equity)}</strong>
        </div>
        <div>
          <span>累计收益率</span>
          <strong>{formatPct(currentSnapshot?.total_return)}</strong>
        </div>
        <div>
          <span>最大回撤</span>
          <strong>{formatPct(currentSnapshot?.max_drawdown)}</strong>
        </div>
        <div>
          <span>成交次数</span>
          <strong>{currentSnapshot ? currentSnapshot.trade_count : '-'}</strong>
        </div>
      </div>
    </section>
  );
}

function ReplayPosition({ selectedName, currentBar, visibleTrades }) {
  const lastTrade = visibleTrades[visibleTrades.length - 1];
  const quantity = lastTrade?.position_after ?? 0;
  const avgCost = lastTrade?.audit?.avg_cost_after_execution;
  const marketValue = currentBar ? quantity * currentBar.close : 0;
  const pnl = Number.isFinite(Number(avgCost)) && currentBar ? (currentBar.close - avgCost) * quantity : null;

  return (
    <section>
      <h3>当前回放持仓</h3>
      <div className="metrics position">
        <div>
          <span>标的</span>
          <strong>{selectedName}</strong>
        </div>
        <div>
          <span>持仓份额</span>
          <strong>{quantity}</strong>
        </div>
        <div>
          <span>当前收盘价</span>
          <strong>{formatNumber(currentBar?.close, 4)}</strong>
        </div>
        <div>
          <span>平均成本</span>
          <strong>{formatNumber(avgCost, 4)}</strong>
        </div>
        <div>
          <span>持仓市值</span>
          <strong>{formatNumber(marketValue)}</strong>
        </div>
        <div>
          <span>估算浮盈亏</span>
          <strong className={valueClass(pnl)}>{formatNumber(pnl)}</strong>
        </div>
      </div>
    </section>
  );
}

function ActivityTable({ title, rows, type }) {
  return (
    <section>
      <h3>{title}</h3>
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>方向</th>
            <th>份额</th>
            <th>{type === 'trade' ? '成交价' : '信号价'}</th>
            <th>{type === 'trade' ? '信号日期' : '状态'}</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan="6" className="empty">当天没有记录</td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={`${type}-${row.datetime}-${row.signal_id ?? index}-${index}`}>
                <td>{row.datetime}</td>
                <td className={row.side}>{sideLabel(row.side)}</td>
                <td>{row.quantity}</td>
                <td>{formatNumber(row.price, 4)}</td>
                <td>
                  {type === 'trade' ? row.signal_datetime : STATUS_LABELS[row.status] ?? row.status}
                </td>
                <td>{row.reject_reason ? rejectLabel(row.reject_reason) : cleanReason(row.reason)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </section>
  );
}

function StrategyCheck({ currentDate, currentBar, currentSnapshot, visibleTrades, visibleSignals }) {
  const filledSignals = visibleSignals.filter((signal) => signal.status === 'filled').length;
  const rejectedSignals = visibleSignals.filter((signal) => signal.status === 'rejected').length;
  const pendingSignals = visibleSignals.filter((signal) => signal.status === 'pending').length;
  const lastSignals = visibleSignals.slice(-8).reverse();
  const todaySignals = visibleSignals.filter((signal) => sameDate(signal, 'datetime', currentDate));
  const todayTrades = visibleTrades.filter((trade) => sameDate(trade, 'datetime', currentDate));

  return (
    <section>
      <h3>策略检查</h3>
      <div className="metrics">
        <div>
          <span>当前收盘价</span>
          <strong>{formatNumber(currentBar?.close, 4)}</strong>
        </div>
        <div>
          <span>当前总资产</span>
          <strong>{formatNumber(currentSnapshot?.total_equity)}</strong>
        </div>
        <div>
          <span>已成交信号/总信号</span>
          <strong>{filledSignals}/{visibleSignals.length}</strong>
        </div>
        <div>
          <span>风控拦截</span>
          <strong>{rejectedSignals}</strong>
        </div>
        <div>
          <span>待次日成交</span>
          <strong>{pendingSignals}</strong>
        </div>
        <div>
          <span>当天成交/信号</span>
          <strong>{todayTrades.length}/{todaySignals.length}</strong>
        </div>
      </div>
      <div className="activity-grid">
        <ActivityTable title="当天信号" rows={todaySignals} type="signal" />
        <ActivityTable title="当天成交" rows={todayTrades} type="trade" />
      </div>
      <h3>最近信号</h3>
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>方向</th>
            <th>份额</th>
            <th>状态</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          {lastSignals.map((row, index) => (
            <tr key={`${row.datetime}-${row.side}-${index}`}>
              <td>{row.datetime}</td>
              <td className={row.side}>{sideLabel(row.side)}</td>
              <td>{row.quantity}</td>
              <td>{STATUS_LABELS[row.status] ?? row.status}</td>
              <td>{row.reject_reason ? rejectLabel(row.reject_reason) : cleanReason(row.reason)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RegimeSummary({ rows }) {
  return (
    <section>
      <h3>行情状态分段</h3>
      <table>
        <thead>
          <tr>
            <th>行情状态</th>
            <th>天数</th>
            <th>策略收益</th>
            <th>70%基准收益</th>
            <th>超额收益</th>
            <th>策略回撤</th>
            <th>成交次数</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.regime}>
              <td>{REGIME_LABELS[row.regime] ?? row.regime_label}</td>
              <td>{row.days}</td>
              <td>{formatPct(row.strategy_return)}</td>
              <td>{formatPct(row.benchmark_return)}</td>
              <td className={valueClass(row.excess_return)}>{formatPct(row.excess_return)}</td>
              <td>{formatPct(row.strategy_max_drawdown)}</td>
              <td>{row.trade_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function OverviewPage({
  currentSnapshot,
  currentBenchmarks,
  visibleEquity,
  visibleBenchmarks,
  regimeRows,
}) {
  return (
    <>
      <AccountOverview currentSnapshot={currentSnapshot} />
      <BenchmarkOverview currentSnapshot={currentSnapshot} currentBenchmarks={currentBenchmarks} />
      <section>
        <h3>策略与基准净值回放</h3>
        <EquityChart rows={visibleEquity} benchmarks={visibleBenchmarks} />
      </section>
      <RegimeSummary rows={regimeRows} />
    </>
  );
}

function EtfDetailPage({
  selectedName,
  visibleBars,
  visibleTrades,
  visibleSignals,
  currentDate,
  currentBar,
  currentSnapshot,
}) {
  return (
    <>
      <KlineChart bars={visibleBars} trades={visibleTrades} signals={visibleSignals} />
      <div className="detail-grid">
        <div>
          <ReplayPosition selectedName={selectedName} currentBar={currentBar} visibleTrades={visibleTrades} />
          <ScenarioComparison currentBar={currentBar} visibleTrades={visibleTrades} />
        </div>
        <StrategyCheck
          currentDate={currentDate}
          currentBar={currentBar}
          currentSnapshot={currentSnapshot}
          visibleTrades={visibleTrades}
          visibleSignals={visibleSignals}
        />
      </div>
    </>
  );
}

function ExperimentPage({ summaryRows, comparisonRows, walkForwardRows }) {
  const selected = summaryRows[0]?.selected_variant ?? '-';
  const train = summaryRows.find((row) => row.split === 'train');
  const validation = summaryRows.find((row) => row.split === 'validation');
  const test = summaryRows.find((row) => row.split === 'test');
  const strategyRows = comparisonRows.filter((row) => row.type === 'strategy' && row.split === 'train');
  const sortedStrategies = [...strategyRows].sort((a, b) => Number(b.score ?? 0) - Number(a.score ?? 0)).slice(0, 8);
  const avgWalkForward =
    walkForwardRows.length > 0
      ? walkForwardRows.reduce((sum, row) => sum + Number(row.excess_return ?? 0), 0) / walkForwardRows.length
      : null;

  return (
    <>
      <section>
        <h3>实验总览</h3>
        <div className="metrics experiment">
          <div>
            <span>训练期选中策略</span>
            <strong>{selected}</strong>
          </div>
          <div>
            <span>训练期超额收益</span>
            <strong className={valueClass(train?.excess_return)}>{formatPct(train?.excess_return)}</strong>
          </div>
          <div>
            <span>验证期超额收益</span>
            <strong className={valueClass(validation?.excess_return)}>{formatPct(validation?.excess_return)}</strong>
          </div>
          <div>
            <span>测试期超额收益</span>
            <strong className={valueClass(test?.excess_return)}>{formatPct(test?.excess_return)}</strong>
          </div>
          <div>
            <span>滚动验证轮数</span>
            <strong>{walkForwardRows.length}</strong>
          </div>
          <div>
            <span>滚动平均超额</span>
            <strong className={valueClass(avgWalkForward)}>{formatPct(avgWalkForward)}</strong>
          </div>
        </div>
      </section>

      <section>
        <h3>训练 / 验证 / 测试</h3>
        <table>
          <thead>
            <tr>
              <th>区间</th>
              <th>策略收益</th>
              <th>70%基准</th>
              <th>超额收益</th>
              <th>策略回撤</th>
              <th>成交</th>
              <th>拦截</th>
            </tr>
          </thead>
          <tbody>
            {summaryRows.map((row) => (
              <tr key={row.split}>
                <td>{row.split}</td>
                <td>{formatPct(row.strategy_total_return)}</td>
                <td>{formatPct(row.benchmark_total_return)}</td>
                <td className={valueClass(row.excess_return)}>{formatPct(row.excess_return)}</td>
                <td>{formatPct(row.strategy_max_drawdown)}</td>
                <td>{row.trades}</td>
                <td>{row.rejected}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>训练期策略排名</h3>
        <table>
          <thead>
            <tr>
              <th>策略版本</th>
              <th>收益</th>
              <th>最大回撤</th>
              <th>分数</th>
              <th>成交</th>
              <th>拦截</th>
            </tr>
          </thead>
          <tbody>
            {sortedStrategies.map((row) => (
              <tr key={`${row.split}-${row.variant}`}>
                <td>{row.variant}</td>
                <td>{formatPct(row.total_return)}</td>
                <td>{formatPct(row.max_drawdown)}</td>
                <td>{formatNumber(row.score, 4)}</td>
                <td>{row.trades}</td>
                <td>{row.rejected}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Walk-forward 滚动验证</h3>
        <table>
          <thead>
            <tr>
              <th>窗口</th>
              <th>训练期</th>
              <th>验证期</th>
              <th>选中策略</th>
              <th>策略收益</th>
              <th>70%基准</th>
              <th>超额收益</th>
              <th>成交</th>
            </tr>
          </thead>
          <tbody>
            {walkForwardRows.map((row) => (
              <tr key={row.window}>
                <td>{row.window}</td>
                <td>{row.train_start} ~ {row.train_end}</td>
                <td>{row.validation_start} ~ {row.validation_end}</td>
                <td>{row.selected_variant}</td>
                <td>{formatPct(row.strategy_total_return)}</td>
                <td>{formatPct(row.benchmark_total_return)}</td>
                <td className={valueClass(row.excess_return)}>{formatPct(row.excess_return)}</td>
                <td>{row.trades}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function App() {
  const [universe, setUniverse] = useState([]);
  const [equityRows, setEquityRows] = useState([]);
  const [benchmarkRows, setBenchmarkRows] = useState([]);
  const [regimeRows, setRegimeRows] = useState([]);
  const [experimentSummary, setExperimentSummary] = useState([]);
  const [experimentComparison, setExperimentComparison] = useState([]);
  const [walkForwardRows, setWalkForwardRows] = useState([]);
  const [bars, setBars] = useState([]);
  const [trades, setTrades] = useState([]);
  const [signals, setSignals] = useState([]);
  const [symbol, setSymbol] = useState('');
  const [activeView, setActiveView] = useState('overview');
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchJson('/api/universe'),
      fetchJson('/api/account/equity'),
      fetchJson('/api/benchmarks/equity'),
      fetchJson('/api/regimes/summary'),
      fetchJson('/api/experiments/summary'),
      fetchJson('/api/experiments/comparison'),
      fetchJson('/api/experiments/walk-forward'),
    ]).then(([universeRows, equityData, benchmarkData, regimeData, experimentSummaryData, experimentComparisonData, walkForwardData]) => {
      setUniverse(universeRows);
      setEquityRows(equityData);
      setBenchmarkRows(benchmarkData);
      setRegimeRows(regimeData);
      setExperimentSummary(experimentSummaryData);
      setExperimentComparison(experimentComparisonData);
      setWalkForwardRows(walkForwardData);
      setPlaybackIndex(Math.max(0, equityData.length - 1));
      setSymbol(universeRows[0]?.symbol ?? '');
    });
  }, []);

  useEffect(() => {
    if (!symbol) return;
    Promise.all([
      fetchJson(`/api/bars?symbol=${symbol}`),
      fetchJson(`/api/trades?symbol=${symbol}`),
      fetchJson(`/api/signals?symbol=${symbol}`),
    ]).then(([barRows, tradeRows, signalRows]) => {
      setBars(barRows);
      setTrades(tradeRows);
      setSignals(signalRows);
    });
  }, [symbol]);

  useEffect(() => {
    if (!playing || equityRows.length === 0) return undefined;
    const id = window.setInterval(() => {
      setPlaybackIndex((current) => {
        if (current >= equityRows.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 650);
    return () => window.clearInterval(id);
  }, [playing, equityRows.length]);

  const selectedName = useMemo(
    () => universe.find((item) => item.symbol === symbol)?.name ?? symbol,
    [universe, symbol],
  );
  const dates = useMemo(() => equityRows.map((row) => row.date), [equityRows]);
  const currentDate = dates[playbackIndex] ?? '';
  const visibleBars = useMemo(
    () => bars.filter((bar) => bar.datetime <= currentDate),
    [bars, currentDate],
  );
  const visibleTrades = useMemo(
    () => trades.filter((trade) => trade.datetime <= currentDate),
    [trades, currentDate],
  );
  const visibleSignals = useMemo(
    () => signals.filter((signal) => signal.datetime <= currentDate),
    [signals, currentDate],
  );
  const visibleEquity = useMemo(
    () => equityRows.filter((row) => dateKeyOf(row.date) <= dateKeyOf(currentDate)),
    [equityRows, currentDate],
  );
  const visibleBenchmarks = useMemo(
    () => benchmarkRows.filter((row) => dateKeyOf(row.date) <= dateKeyOf(currentDate)),
    [benchmarkRows, currentDate],
  );
  const currentBar = visibleBars[visibleBars.length - 1];
  const currentSnapshot = visibleEquity[visibleEquity.length - 1];
  const currentBenchmarks = useMemo(
    () => benchmarkRows.filter((row) => dateKeyOf(row.date) === dateKeyOf(currentDate)),
    [benchmarkRows, currentDate],
  );
  const pageTitle = activeView === 'overview' ? '账户总览' : activeView === 'experiment' ? '实验对比' : selectedName;

  return (
    <main className="shell">
      <aside className="sidebar">
        <h1>ETF 模拟盘</h1>
        <nav className="nav">
          <button className={activeView === 'overview' ? 'active' : ''} onClick={() => setActiveView('overview')}>
            总览
          </button>
          <button className={activeView === 'detail' ? 'active' : ''} onClick={() => setActiveView('detail')}>
            ETF详情
          </button>
          <button className={activeView === 'experiment' ? 'active' : ''} onClick={() => setActiveView('experiment')}>
            实验对比
          </button>
        </nav>
        <h3 className="sidebar-title">标的</h3>
        <div className="list">
          {universe.map((item) => (
            <button
              className={item.symbol === symbol ? 'active' : ''}
              key={item.symbol}
              onClick={() => {
                setSymbol(item.symbol);
                setActiveView('detail');
              }}
            >
              <span>{item.name}</span>
              <strong>{item.symbol}</strong>
            </button>
          ))}
        </div>
      </aside>
      <section className="content">
        <header>
          <div>
            <p>本地模拟回放</p>
            <h2>{pageTitle}</h2>
          </div>
        </header>
        <PlaybackControls
          dates={dates}
          index={playbackIndex}
          playing={playing}
          onIndexChange={(value) => {
            setPlaybackIndex(value);
            setPlaying(false);
          }}
          onPlayingChange={setPlaying}
        />
        {activeView === 'overview' ? (
          <OverviewPage
            currentSnapshot={currentSnapshot}
            currentBenchmarks={currentBenchmarks}
            visibleEquity={visibleEquity}
            visibleBenchmarks={visibleBenchmarks}
            regimeRows={regimeRows}
          />
        ) : activeView === 'experiment' ? (
          <ExperimentPage
            summaryRows={experimentSummary}
            comparisonRows={experimentComparison}
            walkForwardRows={walkForwardRows}
          />
        ) : (
          <EtfDetailPage
            selectedName={selectedName}
            visibleBars={visibleBars}
            visibleTrades={visibleTrades}
            visibleSignals={visibleSignals}
            currentDate={currentDate}
            currentBar={currentBar}
            currentSnapshot={currentSnapshot}
          />
        )}
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
