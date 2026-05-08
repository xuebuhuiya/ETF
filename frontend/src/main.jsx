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

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function KlineChart({ bars, trades }) {
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
      trades.map((trade) => ({
        time: trade.datetime,
        position: trade.side === 'buy' ? 'belowBar' : 'aboveBar',
        color: trade.side === 'buy' ? '#16a34a' : '#dc2626',
        shape: trade.side === 'buy' ? 'arrowUp' : 'arrowDown',
        text: `${trade.side} ${trade.quantity}`,
      })),
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
  }, [bars, trades]);

  return <div id="kline-chart" className="chart" />;
}

function EquityChart({ rows }) {
  useEffect(() => {
    let chart;
    const element = document.getElementById('equity-chart');
    if (rows.length === 0) {
      element.innerHTML = '';
      return undefined;
    }

    chart = echarts.init(element);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 24, top: 24, bottom: 36 },
      xAxis: { type: 'category', data: rows.map((row) => row.date) },
      yAxis: { type: 'value', scale: true },
      series: [
        {
          name: 'Total Equity',
          type: 'line',
          smooth: true,
          data: rows.map((row) => row.total_equity),
          lineStyle: { color: '#2563eb' },
          areaStyle: { color: 'rgba(37, 99, 235, 0.12)' },
        },
      ],
    });

    return () => {
      if (chart) chart.dispose();
    };
  }, [rows]);

  return <div id="equity-chart" className="chart small" />;
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
  const totalReturn = currentSnapshot ? `${(currentSnapshot.total_return * 100).toFixed(2)}%` : '-';
  const maxDrawdown = currentSnapshot ? `${(currentSnapshot.max_drawdown * 100).toFixed(2)}%` : '-';

  return (
    <section>
      <h3>账户总览</h3>
      <div className="metrics account">
        <div>
          <span>现金</span>
          <strong>{currentSnapshot ? currentSnapshot.cash.toFixed(2) : '-'}</strong>
        </div>
        <div>
          <span>持仓市值</span>
          <strong>{currentSnapshot ? currentSnapshot.market_value.toFixed(2) : '-'}</strong>
        </div>
        <div>
          <span>总资产</span>
          <strong>{currentSnapshot ? currentSnapshot.total_equity.toFixed(2) : '-'}</strong>
        </div>
        <div>
          <span>累计收益率</span>
          <strong>{totalReturn}</strong>
        </div>
        <div>
          <span>最大回撤</span>
          <strong>{maxDrawdown}</strong>
        </div>
        <div>
          <span>成交次数</span>
          <strong>{currentSnapshot ? currentSnapshot.trade_count : '-'}</strong>
        </div>
      </div>
    </section>
  );
}

function StrategyCheck({ currentBar, currentSnapshot, visibleTrades, visibleSignals }) {
  const filledSignals = visibleSignals.filter((signal) => signal.status === 'filled').length;
  const rejectedSignals = visibleSignals.filter((signal) => signal.status === 'rejected').length;
  const pendingSignals = visibleSignals.filter((signal) => signal.status === 'pending').length;
  const lastTrades = visibleTrades.slice(-8).reverse();
  const lastSignals = visibleSignals.slice(-8).reverse();

  return (
    <section>
      <h3>策略检查</h3>
      <div className="metrics">
        <div>
          <span>当前收盘价</span>
          <strong>{currentBar ? currentBar.close.toFixed(4) : '-'}</strong>
        </div>
        <div>
          <span>当前总资产</span>
          <strong>{currentSnapshot ? currentSnapshot.total_equity.toFixed(2) : '-'}</strong>
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
      </div>
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
              <td className={row.side}>{row.side === 'buy' ? '买入' : '卖出'}</td>
              <td>{row.quantity}</td>
              <td>{STATUS_LABELS[row.status] ?? row.status}</td>
              <td>{row.reject_reason || row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>当前可见成交</h3>
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>名称</th>
            <th>方向</th>
            <th>份额</th>
            <th>价格</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          {lastTrades.map((row, index) => (
            <tr key={`${row.datetime}-${row.symbol}-${index}`}>
                  <td>{row.datetime}</td>
                  <td>{row.name}</td>
                  <td className={row.side}>{row.side === 'buy' ? '买入' : '卖出'}</td>
                  <td>{row.quantity}</td>
                  <td>{row.price.toFixed(4)}</td>
              <td>{row.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function App() {
  const [universe, setUniverse] = useState([]);
  const [positions, setPositions] = useState([]);
  const [equityRows, setEquityRows] = useState([]);
  const [bars, setBars] = useState([]);
  const [trades, setTrades] = useState([]);
  const [signals, setSignals] = useState([]);
  const [symbol, setSymbol] = useState('');
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    Promise.all([
      fetchJson('/api/universe'),
      fetchJson('/api/positions'),
      fetchJson('/api/account/equity'),
    ]).then(([universeRows, positionRows, equityData]) => {
      setUniverse(universeRows);
      setPositions(positionRows);
      setEquityRows(equityData);
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
    () => equityRows.filter((row) => row.date <= currentDate),
    [equityRows, currentDate],
  );
  const currentBar = visibleBars[visibleBars.length - 1];
  const currentSnapshot = visibleEquity[visibleEquity.length - 1];

  return (
    <main className="shell">
      <aside className="sidebar">
        <h1>ETF 模拟盘</h1>
        <div className="list">
          {universe.map((item) => (
            <button
              className={item.symbol === symbol ? 'active' : ''}
              key={item.symbol}
              onClick={() => setSymbol(item.symbol)}
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
            <h2>{selectedName}</h2>
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
        <KlineChart bars={visibleBars} trades={visibleTrades} />
        <AccountOverview currentSnapshot={currentSnapshot} />
        <div className="grid">
          <section>
            <h3>账户总资产回放</h3>
            <EquityChart rows={visibleEquity} />
          </section>
          <section>
            <h3>当前持仓浮盈亏</h3>
            <table>
              <thead>
                <tr>
                  <th>名称</th>
                  <th>持仓份额</th>
                  <th>浮动盈亏</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((row) => (
                  <tr key={row.symbol}>
                    <td>{row.name}</td>
                    <td>{row.quantity}</td>
                    <td>{row.pnl.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
        <StrategyCheck
          currentBar={currentBar}
          currentSnapshot={currentSnapshot}
          visibleTrades={visibleTrades}
          visibleSignals={visibleSignals}
        />
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
