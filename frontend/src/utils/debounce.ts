// No debounce utility existed anywhere in the app before this -- used by
// EventsContext for both the search input (don't refetch per keystroke)
// and SSE-triggered refetches (a burst of matches shouldn't fire one
// request per event).
export function debounce<Args extends unknown[]>(fn: (...args: Args) => void, delayMs: number): (...args: Args) => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return (...args: Args) => {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delayMs);
  };
}
