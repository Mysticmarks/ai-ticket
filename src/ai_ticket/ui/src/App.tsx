import React, { useEffect, useMemo, useState } from "react";
import MetricsPanel from "./components/MetricsPanel";
import StatusGrid from "./components/StatusGrid";
import HueSlider from "./components/HueSlider";
import HelpDialog from "./components/HelpDialog";
import { useMetricsStream } from "./hooks/useMetricsStream";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import logoUrl from "./assets/logo.svg";

const App: React.FC = () => {
  const { metrics, refresh } = useMetricsStream();
  const [hue, setHue] = useState<number>(() => Number(localStorage.getItem("dashboard-hue")) || 210);
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    document.documentElement.style.setProperty("--accent-hue", hue.toString());
    localStorage.setItem("dashboard-hue", hue.toString());
  }, [hue]);

  const shortcuts = useMemo(
    () => ({
      "?": () => setHelpOpen((value) => !value),
      r: () => refresh(),
      h: () => setHue((value) => (value + 10) % 360),
    }),
    [refresh]
  );

  useKeyboardShortcuts(shortcuts);

  const metricsView = useMemo(() => metrics, [metrics]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="branding">
          <img src={logoUrl} alt="AI Ticket" />
          <h1>AI Ticket Operations</h1>
        </div>
        <div className="controls-bar">
          <HueSlider value={hue} onChange={setHue} />
          <span className="shortcuts-hint">Press ? for keyboard shortcuts</span>
        </div>
      </header>
      <main className="app-content">
        <section className="panel" aria-label="Key metrics">
          <h2>Realtime Metrics</h2>
          <MetricsPanel metrics={metricsView} />
        </section>
        <section className="panel" aria-label="System status">
          <h2>System Status</h2>
          <StatusGrid statuses={metricsView.statusPanels} lastUpdated={metricsView.timestamp} />
        </section>
        <section className="panel" aria-label="Error activity">
          <h2>Recent Errors</h2>
          {metricsView.recentErrors.length === 0 ? (
            <p>No errors reported in the last 15 minutes.</p>
          ) : (
            <ul>
              {metricsView.recentErrors.map((error) => (
                <li key={error.id}>
                  <strong>{error.code}</strong> &mdash; {error.message} ({new Date(error.timestamp).toLocaleTimeString()})
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
      {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
    </div>
  );
};

export default App;
