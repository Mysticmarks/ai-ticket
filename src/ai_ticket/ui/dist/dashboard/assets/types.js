export const EMPTY_METRICS = {
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
