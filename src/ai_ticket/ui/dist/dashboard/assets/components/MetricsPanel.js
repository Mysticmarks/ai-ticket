import React from "https://esm.sh/react@18.2.0";

const numberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});

const MetricsPanel = ({ metrics }) => {
  return (
    React.createElement(
      "div",
      { className: "metrics-grid" },
      React.createElement(
        "div",
        { className: "metric-card", role: "group", "aria-label": "Total requests" },
        React.createElement("span", null, "Total Requests"),
        React.createElement("div", { className: "metric-value" }, metrics.totals.requests),
        React.createElement(
          "div",
          { className: "sparkline", "aria-hidden": true },
          metrics.sparkline.map((value, index) =>
            React.createElement("span", { key: index, style: { height: `${Math.max(8, value * 60)}%` } })
          )
        )
      ),
      React.createElement(
        "div",
        { className: "metric-card", role: "group", "aria-label": "Success rate" },
        React.createElement("span", null, "Success Rate"),
        React.createElement(
          "div",
          { className: "metric-value" },
          metrics.totals.requests === 0
            ? "0%"
            : `${numberFormatter.format((metrics.totals.successes / metrics.totals.requests) * 100)}%`
        ),
        React.createElement(
          "p",
          null,
          `${metrics.totals.successes} successes / ${metrics.totals.errors} errors`
        )
      ),
      React.createElement(
        "div",
        { className: "metric-card", role: "group", "aria-label": "Latency" },
        React.createElement("span", null, "Latency (avg / p95)"),
        React.createElement(
          "div",
          { className: "metric-value" },
          `${numberFormatter.format(metrics.latency.average)}ms / ${numberFormatter.format(metrics.latency.p95)}ms`
        ),
        React.createElement("p", null, `p50: ${numberFormatter.format(metrics.latency.p50)}ms`)
      ),
      React.createElement(
        "div",
        { className: "metric-card", role: "group", "aria-label": "Throughput" },
        React.createElement("span", null, "Throughput"),
        React.createElement(
          "div",
          { className: "metric-value" },
          `${numberFormatter.format(metrics.throughput.perMinute)} / min`
        ),
        React.createElement("p", null, `${numberFormatter.format(metrics.throughput.perSecond)} / sec`)
      )
    )
  );
};

export default MetricsPanel;
