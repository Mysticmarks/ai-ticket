export type StatusPanel = {
  id: string;
  label: string;
  state: "online" | "degraded" | "offline";
  message: string;
};

export type MetricsSnapshot = {
  timestamp: string;
  totals: {
    requests: number;
    successes: number;
    errors: number;
  };
  latency: {
    average: number;
    p50: number;
    p95: number;
  };
  throughput: {
    perSecond: number;
    perMinute: number;
  };
  sparkline: number[];
  statusPanels: StatusPanel[];
  recentErrors: Array<{
    id: string;
    code: string;
    message: string;
    timestamp: string;
  }>;
};

export const EMPTY_METRICS: MetricsSnapshot = {
  timestamp: new Date(0).toISOString(),
  totals: {
    requests: 0,
    successes: 0,
    errors: 0,
  },
  latency: {
    average: 0,
    p50: 0,
    p95: 0,
  },
  throughput: {
    perSecond: 0,
    perMinute: 0,
  },
  sparkline: [],
  statusPanels: [],
  recentErrors: [],
};
