import { useCallback, useEffect, useRef, useState } from "react";
import { EMPTY_METRICS, type MetricsSnapshot } from "../types";

type MetricsState = {
  metrics: MetricsSnapshot;
  refresh: () => Promise<void>;
};

const METRICS_ENDPOINT = "/api/metrics/summary";
const STREAM_ENDPOINT = "/api/metrics/stream";

export const useMetricsStream = (): MetricsState => {
  const [metrics, setMetrics] = useState<MetricsSnapshot>(EMPTY_METRICS);
  const eventSourceRef = useRef<EventSource | null>(null);
  const fallbackTimerRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const fetchSnapshot = useCallback(async () => {
    const response = await fetch(METRICS_ENDPOINT, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Failed to load metrics: ${response.statusText}`);
    }
    const data = (await response.json()) as MetricsSnapshot;
    setMetrics(data);
  }, []);

  useEffect(() => {
    fetchSnapshot().catch((error) => console.error(error));

    const connectStream = () => {
      const source = new EventSource(STREAM_ENDPOINT);
      eventSourceRef.current = source;

      source.onmessage = (event) => {
        const data = JSON.parse(event.data) as MetricsSnapshot;
        setMetrics(data);
        if (fallbackTimerRef.current) {
          window.clearInterval(fallbackTimerRef.current);
          fallbackTimerRef.current = null;
        }
        if (reconnectTimerRef.current) {
          window.clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
      };

      source.onerror = () => {
        source.close();
        eventSourceRef.current = null;
        if (fallbackTimerRef.current === null) {
          fallbackTimerRef.current = window.setInterval(() => {
            fetchSnapshot().catch((error) => console.error(error));
          }, 10_000);
        }
        if (reconnectTimerRef.current === null) {
          reconnectTimerRef.current = window.setTimeout(() => {
            reconnectTimerRef.current = null;
            connectStream();
          }, 15_000);
        }
      };
    };

    connectStream();

    return () => {
      eventSourceRef.current?.close();
      if (fallbackTimerRef.current) {
        window.clearInterval(fallbackTimerRef.current);
        fallbackTimerRef.current = null;
      }
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [fetchSnapshot]);

  const refresh = useCallback(async () => {
    await fetchSnapshot();
  }, [fetchSnapshot]);

  return { metrics, refresh };
};
