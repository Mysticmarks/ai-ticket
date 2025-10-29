import React, { useMemo } from "https://esm.sh/react@18.2.0";

const formatTimestamp = (timestamp) => {
  const formatter = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return formatter.format(new Date(timestamp));
};

const HistoryExplorer = ({
  history,
  activeSnapshot,
  selectedTimestamp,
  onSelectTimestamp,
  onStepBackward,
  onStepForward,
  isLive,
  followLive,
  onFollowLiveChange,
  onJumpToLive,
}) => {
  const rangeConfig = useMemo(() => {
    if (history.length === 0) {
      return { min: 0, max: 0, value: 0 };
    }

    const selectedIndex = selectedTimestamp
      ? history.findIndex((snapshot) => snapshot.timestamp === selectedTimestamp)
      : history.length - 1;

    return {
      min: 0,
      max: Math.max(history.length - 1, 0),
      value: selectedIndex === -1 ? history.length - 1 : selectedIndex,
    };
  }, [history, selectedTimestamp]);

  const handleSliderChange = (event) => {
    const index = Number(event.target.value);
    const snapshot = history[index];
    if (!snapshot) {
      return;
    }
    if (index === history.length - 1) {
      onSelectTimestamp(null);
    } else {
      onSelectTimestamp(snapshot.timestamp);
    }
  };

  return React.createElement(
    "div",
    { className: "history-explorer", "data-testid": "history-explorer" },
    React.createElement(
      "header",
      { className: "history-header" },
      React.createElement(
        "div",
        null,
        React.createElement("span", { className: "history-pill", "data-live": isLive }, isLive ? "Live" : "Historical"),
        React.createElement(
          "h3",
          null,
          isLive ? "Following live updates" : `Snapshot from ${formatTimestamp(activeSnapshot.timestamp)}`
        ),
        React.createElement(
          "p",
          null,
          `Navigate through the last ${history.length} updates to compare trends in throughput, latency, and error rates. Use the arrow keys or bracket shortcuts to travel through time.`
        )
      ),
      React.createElement(
        "div",
        { className: "history-controls" },
        React.createElement(
          "button",
          { type: "button", className: "ghost-button", onClick: onStepBackward, "aria-label": "Previous snapshot" },
          "◀"
        ),
        React.createElement("input", {
          type: "range",
          "aria-label": "Explore historical snapshots",
          min: rangeConfig.min,
          max: rangeConfig.max,
          value: rangeConfig.value,
          onChange: handleSliderChange,
        }),
        React.createElement(
          "button",
          { type: "button", className: "ghost-button", onClick: onStepForward, "aria-label": "Next snapshot" },
          "▶"
        )
      )
    ),
    React.createElement(
      "div",
      { className: "history-summary" },
      React.createElement(
        "div",
        null,
        React.createElement("span", { className: "summary-label" }, "Requests"),
        React.createElement("strong", null, activeSnapshot.totals.requests.toLocaleString())
      ),
      React.createElement(
        "div",
        null,
        React.createElement("span", { className: "summary-label" }, "Success Rate"),
        React.createElement(
          "strong",
          null,
          activeSnapshot.totals.requests === 0
            ? "0%"
            : `${((activeSnapshot.totals.successes / activeSnapshot.totals.requests) * 100).toFixed(2)}%`
        )
      ),
      React.createElement(
        "div",
        null,
        React.createElement("span", { className: "summary-label" }, "Latency p95"),
        React.createElement("strong", null, `${activeSnapshot.latency.p95.toFixed(0)}ms`)
      ),
      React.createElement(
        "div",
        null,
        React.createElement("span", { className: "summary-label" }, "Errors"),
        React.createElement("strong", null, activeSnapshot.totals.errors.toLocaleString())
      )
    ),
    React.createElement(
      "footer",
      { className: "history-footer" },
      React.createElement(
        "label",
        { className: "toggle", "data-testid": "follow-live-toggle" },
        React.createElement("input", {
          type: "checkbox",
          checked: followLive,
          onChange: (event) => onFollowLiveChange(event.target.checked),
        }),
        React.createElement("span", null, "Automatically follow new snapshots")
      ),
      React.createElement(
        "div",
        { className: "history-footer-actions" },
        React.createElement(
          "button",
          { type: "button", className: "ghost-button", onClick: onJumpToLive, disabled: isLive },
          "Jump to live"
        ),
        React.createElement(
          "button",
          { type: "button", className: "ghost-button", onClick: onStepForward },
          "Step forward"
        )
      )
    )
  );
};

export default HistoryExplorer;
