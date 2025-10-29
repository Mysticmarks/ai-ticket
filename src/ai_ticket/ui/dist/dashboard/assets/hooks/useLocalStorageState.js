import { useEffect, useState } from "https://esm.sh/react@18.2.0";

const isBrowser = typeof window !== "undefined" && typeof window.localStorage !== "undefined";

const defaultSerialize = (value) => JSON.stringify(value);
const defaultDeserialize = (raw) => JSON.parse(raw);

export const useLocalStorageState = (key, defaultValue, options = {}) => {
  const { serialize = defaultSerialize, deserialize = defaultDeserialize } = options;

  const [state, setState] = useState(() => {
    if (!isBrowser) {
      return defaultValue;
    }

    try {
      const storedValue = window.localStorage.getItem(key);
      if (storedValue === null) {
        return defaultValue;
      }
      return deserialize(storedValue);
    } catch (error) {
      console.warn(`Failed to read localStorage key "${key}":`, error);
      return defaultValue;
    }
  });

  useEffect(() => {
    if (!isBrowser) {
      return;
    }

    try {
      const serialized = serialize(state);
      window.localStorage.setItem(key, serialized);
    } catch (error) {
      console.warn(`Failed to persist localStorage key "${key}":`, error);
    }
  }, [key, serialize, state]);

  return [state, setState];
};
