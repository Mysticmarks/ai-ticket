import { useCallback, useEffect, useRef, useState } from "https://esm.sh/react@18.2.0";
import { EMPTY_METRICS } from "../types.js";

const METRICS_ENDPOINT = "/api/metrics/summary";
const STREAM_ENDPOINT = "/api/metrics/stream";

export const useMetricsStream = ({ paused = false } = {}) => {
  const [metrics, setMetrics] = useState(EMPTY_METRICS);
  const eventSourceRef = useRef(null);
  const fallbackTimerRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  const cleanupTimers = useCallback(() => {
    if (fallbackTimerRef.current !== null) {
      window.clearInterval(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const fetchSnapshot = useCallback(async () => {
    const response = await fetch(METRICS_ENDPOINT, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Failed to load metrics: ${response.statusText}`);
    }
    const data = await response.json();
    setMetrics(data);
  }, []);

  useEffect(() => {
    fetchSnapshot().catch((error) => console.error(error));
  }, [fetchSnapshot]);

  useEffect(() => {
    if (paused) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      cleanupTimers();
      return;
    }

    const connectStream = () => {
      const source = new EventSource(STREAM_ENDPOINT);
      eventSourceRef.current = source;

      source.onmessage = (event) => {
        const data = JSON.parse(event.data);
        setMetrics(data);
        cleanupTimers();
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
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      cleanupTimers();
    };
  }, [cleanupTimers, fetchSnapshot, paused]);

  const refresh = useCallback(async () => {
    await fetchSnapshot();
  }, [fetchSnapshot]);

  return { metrics, refresh };
};
