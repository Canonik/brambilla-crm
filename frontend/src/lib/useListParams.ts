import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

/** List filters kept in the URL so views can be shared and survive reloads. */
export function useListParams<K extends string>(keys: readonly K[], defaults: Partial<Record<K, string>> = {}) {
  const [params, setParams] = useSearchParams();
  const values = useMemo(() => {
    const out = {} as Record<K, string>;
    for (const k of keys) out[k] = params.get(k) ?? defaults[k] ?? "";
    return out;
  }, [params, keys, defaults]);

  const set = useCallback(
    (patch: Partial<Record<K, string>>) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(patch) as Array<[K, string | undefined]>) {
            if (!v || v === defaults[k]) next.delete(k);
            else next.set(k, v);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams, defaults],
  );

  return [values, set] as const;
}
