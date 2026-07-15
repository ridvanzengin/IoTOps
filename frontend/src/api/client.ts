const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Set once by DemoModeContext on mount. 403 has no source in this backend
// other than the demo-mode guard (every mutating/AI route), so calling
// this on every 403 is safe -- there's no other case to distinguish.
let demoBlockNotifier: ((message: string) => void) | null = null;

export function registerDemoBlockNotifier(callback: (message: string) => void): void {
  demoBlockNotifier = callback;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message = body?.detail ?? `Request failed with status ${response.status}`;
    if (response.status === 403) {
      demoBlockNotifier?.(message);
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
