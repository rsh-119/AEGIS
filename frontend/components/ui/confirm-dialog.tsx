"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type ConfirmOptions = {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
};

type ConfirmContextValue = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ConfirmOptions | null>(null);
  const [mounted, setMounted] = useState(false);
  const resolver = useRef<((v: boolean) => void) | null>(null);

  useEffect(() => { setMounted(true); }, []);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve;
      setState(options);
    });
  }, []);

  function close(result: boolean) {
    resolver.current?.(result);
    setState(null);
  }

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {mounted && createPortal(
        <>
          <div
            aria-hidden
            className={clsx(
              "fixed inset-0 z-[90] bg-black/50 backdrop-blur-[3px] transition-opacity duration-200",
              state ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
            )}
            onClick={() => close(false)}
          />
          <div
            className={clsx(
              "fixed left-1/2 top-1/2 z-[100] w-[90vw] max-w-sm -translate-x-1/2 -translate-y-1/2 transition-all duration-200",
              state ? "scale-100 opacity-100 pointer-events-auto" : "scale-90 opacity-0 pointer-events-none"
            )}
          >
            {state && (
              <Card className="p-5 shadow-[0_25px_70px_-12px_rgba(0,0,0,0.55)]">
                <div className="flex items-start gap-3">
                  {state.destructive && (
                    <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-down/10">
                      <AlertTriangle className="h-4.5 w-4.5 text-down" />
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-fg">{state.title}</p>
                    {state.description && (
                      <p className="mt-1 text-sm text-muted">{state.description}</p>
                    )}
                  </div>
                </div>
                <div className="mt-4 flex justify-end gap-2">
                  <Button variant="ghost" onClick={() => close(false)}>
                    {state.cancelLabel ?? "Cancel"}
                  </Button>
                  <Button
                    onClick={() => close(true)}
                    className={state.destructive ? "!bg-down hover:!brightness-90" : ""}
                  >
                    {state.confirmLabel ?? "Confirm"}
                  </Button>
                </div>
              </Card>
            )}
          </div>
        </>,
        document.body
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmContextValue {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used inside ConfirmProvider");
  return ctx;
}
