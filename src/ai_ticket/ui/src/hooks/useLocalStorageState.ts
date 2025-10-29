import { useEffect, useState } from "react";

type Deserialize<T> = (raw: string) => T;
type Serialize<T> = (value: T) => string;

const isBrowser = typeof window !== "undefined" && typeof window.localStorage !== "undefined";

const defaultSerialize = <T,>(value: T) => JSON.stringify(value);
const defaultDeserialize = <T,>(raw: string): T => JSON.parse(raw) as T;

export const useLocalStorageState = <T,>(
  key: string,
  defaultValue: T,
  options: { serialize?: Serialize<T>; deserialize?: Deserialize<T> } = {}
) => {
  const { serialize = defaultSerialize, deserialize = defaultDeserialize } = options;

  const [state, setState] = useState<T>(() => {
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

  return [state, setState] as const;
};
