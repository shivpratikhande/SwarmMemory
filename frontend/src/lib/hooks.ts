"use client";

import useSWR, { type SWRConfiguration } from "swr";

import { fetcher, type AppConfig } from "./api";

/** Live data: polls the API so agent/chain activity shows up without reloads. */
export function useLive<T>(path: string | null, interval = 2500, opts: SWRConfiguration = {}) {
  return useSWR<T>(path, fetcher, { refreshInterval: interval, revalidateOnFocus: true, keepPreviousData: true, ...opts });
}

export function useConfig() {
  return useSWR<AppConfig>("/config", fetcher, { revalidateOnFocus: false });
}
