import React from "https://esm.sh/react@18.2.0";

const StatusGrid = ({ statuses, lastUpdated }) => {
  const lastUpdatedLabel = lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : "N/A";

  return React.createElement(
    "div",
    { className: "status-grid", role: "list", "aria-label": "System status panels" },
    statuses.map((status) =>
      React.createElement(
        "article",
        { key: status.id, className: "status-card", "data-state": status.state, role: "listitem" },
        React.createElement("div", { className: "status-label" }, status.label),
        React.createElement("div", { className: "status-pill" }, status.state),
        React.createElement("p", null, status.message)
      )
    ),
    React.createElement(
      "footer",
      { className: "status-card", "data-state": "online" },
      React.createElement("div", { className: "status-label" }, "Last Updated"),
      React.createElement("div", { className: "status-pill" }, lastUpdatedLabel),
      React.createElement("p", null, "Live updates are delivered via server-sent events with automatic fallback polling.")
    )
  );
};

export default StatusGrid;
