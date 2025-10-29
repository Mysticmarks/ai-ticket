import React, { useMemo } from "react";
import type { MetricsSnapshot } from "../types";

type HistoryExplorerProps = {
  history: MetricsSnapshot[];
  activeSnapshot: MetricsSnapshot;
  selectedTimestamp: string | null;
  onSelectTimestamp: (timestamp: string | null) => void;
  onStepBackward: () => void;
  onStepForward: () => void;
  isLive: boolean;
  followLive: boolean;
  onFollowLiveChange: (follow: boolean) => void;
  onJumpToLive: () => void;
};

const formatTimestamp = (timestamp: string) => {
  const formatter = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return formatter.format(new Date(timestamp));
};

const HistoryExplorer: React.FC<HistoryExplorerProps> = ({
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

  const handleSliderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
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

  return (
    <div className="history-explorer" data-testid="history-explorer">
      <header className="history-header">
        <div>
          <span className="history-pill" data-live={isLive}>
            {isLive ? "Live" : "Historical"}
          </span>
          <h3>{isLive ? "Following live updates" : `Snapshot from ${formatTimestamp(activeSnapshot.timestamp)}`}</h3>
          <p>
            Navigate through the last {history.length} updates to compare trends in throughput, latency, and error rates. Use
            the arrow keys or bracket shortcuts to travel through time.
          </p>
        </div>
        <div className="history-controls">
          <button type="button" className="ghost-button" onClick={onStepBackward} aria-label="Previous snapshot">
            ◀
          </button>
          <input
            type="range"
            aria-label="Explore historical snapshots"
            min={rangeConfig.min}
            max={rangeConfig.max}
            value={rangeConfig.value}
            onChange={handleSliderChange}
          />
          <button type="button" className="ghost-button" onClick={onStepForward} aria-label="Next snapshot">
            ▶
          </button>
        </div>
      </header>
      <div className="history-summary">
        <div>
          <span className="summary-label">Requests</span>
          <strong>{activeSnapshot.totals.requests.toLocaleString()}</strong>
        </div>
        <div>
          <span className="summary-label">Success Rate</span>
          <strong>
            {activeSnapshot.totals.requests === 0
              ? "0%"
              : `${((activeSnapshot.totals.successes / activeSnapshot.totals.requests) * 100).toFixed(2)}%`}
          </strong>
        </div>
        <div>
          <span className="summary-label">Latency p95</span>
          <strong>{activeSnapshot.latency.p95.toFixed(0)}ms</strong>
        </div>
        <div>
          <span className="summary-label">Errors</span>
          <strong>{activeSnapshot.totals.errors.toLocaleString()}</strong>
        </div>
      </div>
      <footer className="history-footer">
        <label className="toggle" data-testid="follow-live-toggle">
          <input
            type="checkbox"
            checked={followLive}
            onChange={(event) => onFollowLiveChange(event.target.checked)}
          />
          <span>Automatically follow new snapshots</span>
        </label>
        <div className="history-footer-actions">
          <button type="button" className="ghost-button" onClick={onJumpToLive} disabled={isLive}>
            Jump to live
          </button>
          <button type="button" className="ghost-button" onClick={onStepForward}>
            Step forward
          </button>
        </div>
      </footer>
    </div>
  );
};

export default HistoryExplorer;
