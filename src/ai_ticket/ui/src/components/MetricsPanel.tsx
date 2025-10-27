import React from "react";
import type { MetricsSnapshot } from "../types";

type MetricsPanelProps = {
  metrics: MetricsSnapshot;
};

const numberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});

const MetricsPanel: React.FC<MetricsPanelProps> = ({ metrics }) => {
  return (
    <div className="metrics-grid">
      <div className="metric-card" role="group" aria-label="Total requests">
        <span>Total Requests</span>
        <div className="metric-value">{metrics.totals.requests}</div>
        <div className="sparkline" aria-hidden>
          {metrics.sparkline.map((value, index) => (
            <span key={index} style={{ height: `${Math.max(8, value * 60)}%` }} />
          ))}
        </div>
      </div>
      <div className="metric-card" role="group" aria-label="Success rate">
        <span>Success Rate</span>
        <div className="metric-value">
          {metrics.totals.requests === 0
            ? "0%"
            : `${numberFormatter.format((metrics.totals.successes / metrics.totals.requests) * 100)}%`}
        </div>
        <p>
          {metrics.totals.successes} successes / {metrics.totals.errors} errors
        </p>
      </div>
      <div className="metric-card" role="group" aria-label="Latency">
        <span>Latency (avg / p95)</span>
        <div className="metric-value">
          {numberFormatter.format(metrics.latency.average)}ms / {numberFormatter.format(metrics.latency.p95)}ms
        </div>
        <p>p50: {numberFormatter.format(metrics.latency.p50)}ms</p>
      </div>
      <div className="metric-card" role="group" aria-label="Throughput">
        <span>Throughput</span>
        <div className="metric-value">{numberFormatter.format(metrics.throughput.perMinute)} / min</div>
        <p>{numberFormatter.format(metrics.throughput.perSecond)} / sec</p>
      </div>
    </div>
  );
};

export default MetricsPanel;
