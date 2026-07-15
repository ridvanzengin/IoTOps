import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { registerDemoBlockNotifier } from "../api/client";

interface DemoModeContextValue {
  toastMessage: string | null;
  dismissToast: () => void;
}

const DemoModeContext = createContext<DemoModeContextValue | null>(null);

export function DemoModeProvider({ children }: { children: ReactNode }) {
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    registerDemoBlockNotifier((message) => {
      setToastMessage(message);
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
      dismissTimer.current = setTimeout(() => setToastMessage(null), 4000);
    });
  }, []);

  function dismissToast() {
    if (dismissTimer.current) clearTimeout(dismissTimer.current);
    setToastMessage(null);
  }

  return (
    <DemoModeContext.Provider value={{ toastMessage, dismissToast }}>
      {children}
    </DemoModeContext.Provider>
  );
}

export function useDemoMode(): DemoModeContextValue {
  const context = useContext(DemoModeContext);
  if (!context) throw new Error("useDemoMode must be used within a DemoModeProvider");
  return context;
}
