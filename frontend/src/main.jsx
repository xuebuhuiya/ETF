import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { createChart, createSeriesMarkers, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import * as echarts from 'echarts';
import './styles.css';

const API_BASE = 'http://127.0.0.1:8000';

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function KlineChart({ symbol }) {
  useEffect(() => {
    if (!symbol) return;

    let chart;
    let disposed = false;
    const element = document.getElementById('kline-chart');
    element.innerHTML = '';

    Promise.all([
      fetchJson(`/api/bars?symbol=${symbol}`),
      fetchJson(`/api/trades?symbol=${symbol}`),
    ]).then(([bars, trades]) => {
      if (disposed) return;
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
    });

    return () => {
      disposed = true;
      if (chart) chart.remove();
    };
  }, [symbol]);

  return <div id="kline-chart" className="chart" />;
}

function EquityChart() {
  useEffect(() => {
    let chart;
    let disposed = false;
    const element = document.getElementById('equity-chart');
    fetchJson('/api/account/equity').then((rows) => {
      if (disposed) return;
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
    });
    return () => {
      disposed = true;
      if (chart) chart.dispose();
    };
  }, []);

  return <div id="equity-chart" className="chart small" />;
}

function App() {
  const [universe, setUniverse] = useState([]);
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [symbol, setSymbol] = useState('');

  useEffect(() => {
    Promise.all([
      fetchJson('/api/universe'),
      fetchJson('/api/positions'),
      fetchJson('/api/trades'),
    ]).then(([universeRows, positionRows, tradeRows]) => {
      setUniverse(universeRows);
      setPositions(positionRows);
      setTrades(tradeRows.slice(-20).reverse());
      setSymbol(universeRows[0]?.symbol ?? '');
    });
  }, []);

  const selectedName = useMemo(
    () => universe.find((item) => item.symbol === symbol)?.name ?? symbol,
    [universe, symbol],
  );

  return (
    <main className="shell">
      <aside className="sidebar">
        <h1>ETF Sim</h1>
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
            <p>Local Simulation</p>
            <h2>{selectedName}</h2>
          </div>
        </header>
        <KlineChart symbol={symbol} />
        <div className="grid">
          <section>
            <h3>Account Equity</h3>
            <EquityChart />
          </section>
          <section>
            <h3>Positions</h3>
            <table>
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
        <section>
          <h3>Recent Trades</h3>
          <table>
            <tbody>
              {trades.map((row, index) => (
                <tr key={`${row.datetime}-${row.symbol}-${index}`}>
                  <td>{row.datetime}</td>
                  <td>{row.name}</td>
                  <td className={row.side}>{row.side}</td>
                  <td>{row.quantity}</td>
                  <td>{row.price.toFixed(4)}</td>
                  <td>{row.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
