import React from "react";
import type { StatusPanel } from "../types";

type StatusGridProps = {
  statuses: StatusPanel[];
  lastUpdated: string;
};

const StatusGrid: React.FC<StatusGridProps> = ({ statuses, lastUpdated }) => {
  const lastUpdatedLabel = lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : "N/A";

  return (
    <div className="status-grid" role="list" aria-label="System status panels">
      {statuses.map((status) => (
        <article key={status.id} className="status-card" data-state={status.state} role="listitem">
          <div className="status-label">{status.label}</div>
          <div className="status-pill">{status.state}</div>
          <p>{status.message}</p>
        </article>
      ))}
      <footer className="status-card" data-state="online">
        <div className="status-label">Last Updated</div>
        <div className="status-pill">{lastUpdatedLabel}</div>
        <p>Live updates are delivered via server-sent events with automatic fallback polling.</p>
      </footer>
    </div>
  );
};

export default StatusGrid;
