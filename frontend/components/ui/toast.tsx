"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";
import { clsx } from "clsx";

type ToastVariant = "success" | "error" | "info" | "warning";
type Toast = { id: number; variant: ToastVariant; title: string; description?: string };

interface ToastContextValue {
  toast: (t: { variant?: ToastVariant; title: string; description?: string; duration?: number }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const VARIANT_STYLE: Record<ToastVariant, { icon: React.ReactNode; accent: string }> = {
  success: { icon: <CheckCircle2 className="h-5 w-5 text-up" />,      accent: "border-l-up" },
  error:   { icon: <XCircle className="h-5 w-5 text-down" />,        accent: "border-l-down" },
  warning: { icon: <AlertTriangle className="h-5 w-5 text-saffron" />, accent: "border-l-saffron" },
  info:    { icon: <Info className="h-5 w-5 text-blue-500" />,        accent: "border-l-blue-500" },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [mounted, setMounted] = useState(false);
  const nextId = useRef(0);

  useEffect(() => { setMounted(true); }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const toast = useCallback(({ variant = "info", title, description, duration = 4000 }: {
    variant?: ToastVariant; title: string; description?: string; duration?: number;
  }) => {
    const id = nextId.current++;
    setToasts((t) => [...t, { id, variant, title, description }]);
    setTimeout(() => dismiss(id), duration);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {mounted && createPortal(
        <div className="fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2 sm:bottom-6 sm:right-6">
          {toasts.map((t) => {
            const style = VARIANT_STYLE[t.variant];
            return (
              <div
                key={t.id}
                className={clsx(
                  "animate-fade-up flex items-start gap-3 rounded-xl border border-l-4 bg-surface p-3.5 shadow-lg",
                  style.accent
                )}
              >
                <span className="mt-0.5 shrink-0">{style.icon}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-fg">{t.title}</p>
                  {t.description && <p className="mt-0.5 text-xs text-muted">{t.description}</p>}
                </div>
                <button
                  onClick={() => dismiss(t.id)}
                  className="shrink-0 rounded-lg p-1 text-muted transition-colors hover:bg-raised hover:text-fg"
                  aria-label="Dismiss"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
