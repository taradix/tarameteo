import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

// Fresh client per test so cached queries never leak between tests.
export function queryWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

// Stub fetch with a handler mapping a request path (with query string) to a JSON body.
// Unmatched paths answer 404.
export function stubFetch(routes: Record<string, unknown>) {
  const fetch = vi.fn(async (input: string | URL | Request) => {
    const path = String(input);
    const key = Object.keys(routes).find((k) => path.split("?")[0] === k);
    return key === undefined
      ? new Response(null, { status: 404, statusText: "Not Found" })
      : Response.json(routes[key]);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

// happy-dom has no EventSource; this one records instances so tests can push messages.
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  closed = false;
  readonly url: string;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  emit(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }

  close() {
    this.closed = true;
  }
}

export function stubEventSource() {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  return FakeEventSource.instances;
}
