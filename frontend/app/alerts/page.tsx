"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { fetcher, inr, pct, del, post, patch } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { Bell, BellOff, Pencil, Trash2, Plus, CheckCircle2 } from "lucide-react";
import clsx from "clsx";

interface Alert {
  id: number;
  ticker: string;
  company_name: string | null;
  alert_type: "above" | "below";
  target_price: number;
  is_active: boolean;
  triggered_at: string | null;
  created_at: string;
}

const ALERTS_URL = "/api/alerts";

export default function AlertsPage() {
  const { data, isLoading } = useSWR<{ alerts: Alert[] }>(ALERTS_URL, fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 30_000,   // poll every 30s so triggered alerts appear
  });

  const [ticker, setTicker]   = useState("");
  const [type, setType]       = useState<"above" | "below">("above");
  const [price, setPrice]     = useState("");
  const [busy, setBusy]       = useState(false);
  const [editId, setEditId]   = useState<number | null>(null);
  const [editPrice, setEditPrice] = useState("");

  const alerts = data?.alerts ?? [];
  const active   = alerts.filter(a => a.is_active && !a.triggered_at);
  const triggered = alerts.filter(a => a.triggered_at);
  const inactive = alerts.filter(a => !a.is_active && !a.triggered_at);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker || !price) return;
    setBusy(true);
    try {
      await post(ALERTS_URL, { ticker, alert_type: type, target_price: parseFloat(price) });
      setTicker(""); setPrice("");
      mutate(ALERTS_URL);
    } catch (err) { alert((err as Error).message); }
    finally { setBusy(false); }
  }

  async function remove(id: number) {
    if (!confirm("Delete this alert?")) return;
    await del(`${ALERTS_URL}/${id}`);
    mutate(ALERTS_URL);
  }

  async function dismiss(id: number) {
    await post(`${ALERTS_URL}/${id}/dismiss`, {});
    mutate(ALERTS_URL);
  }

  async function saveEdit(id: number) {
    if (!editPrice) return;
    await patch(`${ALERTS_URL}/${id}`, { target_price: parseFloat(editPrice) });
    setEditId(null); setEditPrice("");
    mutate(ALERTS_URL);
  }

  async function toggle(a: Alert) {
    await patch(`${ALERTS_URL}/${a.id}`, { is_active: !a.is_active });
    mutate(ALERTS_URL);
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex items-center gap-2">
        <Bell className="h-5 w-5 text-saffron" />
        <h1 className="font-display text-3xl font-semibold">Price Alerts</h1>
      </div>

      {/* Create form */}
      <div className="card p-5">
        <h2 className="mb-4 flex items-center gap-2 font-medium text-sm">
          <Plus className="h-4 w-4 text-saffron" /> New Alert
        </h2>
        <form onSubmit={create} className="grid gap-3 sm:grid-cols-4">
          <div className="sm:col-span-2">
            <SearchBox
              placeholder="Search stock (TCS, INFY…)"
              onSelect={(sym) => setTicker(sym)}
            />
            {ticker && <p className="mt-1 text-xs text-saffron font-mono">{ticker}</p>}
          </div>
          <select
            value={type}
            onChange={e => setType(e.target.value as "above" | "below")}
            className="input"
          >
            <option value="above">Price Above ↑</option>
            <option value="below">Price Below ↓</option>
          </select>
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Target price (₹)"
            value={price}
            onChange={e => setPrice(e.target.value)}
            className="input"
            required
          />
          <button
            type="submit"
            disabled={busy || !ticker}
            className="btn-primary sm:col-span-4 flex items-center justify-center gap-2"
          >
            <Bell className="h-4 w-4" />
            {busy ? "Creating…" : "Set Alert"}
          </button>
        </form>
      </div>

      {isLoading ? (
        <div className="card p-8 text-center text-muted animate-pulse">Loading alerts…</div>
      ) : alerts.length === 0 ? (
        <div className="card p-10 text-center text-muted">
          <Bell className="mx-auto h-10 w-10 mb-3 opacity-20" />
          <p>No alerts yet. Set your first alert above.</p>
        </div>
      ) : (
        <>
          {/* Triggered alerts */}
          {triggered.length > 0 && (
            <AlertTable
              title="Triggered"
              titleColor="text-up"
              alerts={triggered}
              onDelete={remove}
              onDismiss={dismiss}
              onToggle={toggle}
              editId={editId}
              editPrice={editPrice}
              setEditId={setEditId}
              setEditPrice={setEditPrice}
              onSaveEdit={saveEdit}
            />
          )}

          {/* Active alerts */}
          {active.length > 0 && (
            <AlertTable
              title="Active"
              titleColor="text-foreground"
              alerts={active}
              onDelete={remove}
              onDismiss={dismiss}
              onToggle={toggle}
              editId={editId}
              editPrice={editPrice}
              setEditId={setEditId}
              setEditPrice={setEditPrice}
              onSaveEdit={saveEdit}
            />
          )}

          {/* Paused alerts */}
          {inactive.length > 0 && (
            <AlertTable
              title="Paused"
              titleColor="text-muted"
              alerts={inactive}
              onDelete={remove}
              onDismiss={dismiss}
              onToggle={toggle}
              editId={editId}
              editPrice={editPrice}
              setEditId={setEditId}
              setEditPrice={setEditPrice}
              onSaveEdit={saveEdit}
            />
          )}
        </>
      )}
    </div>
  );
}

// ── Alert table sub-component ──────────────────────────────────────────────────

function AlertTable({
  title, titleColor, alerts, onDelete, onDismiss, onToggle,
  editId, editPrice, setEditId, setEditPrice, onSaveEdit,
}: {
  title: string;
  titleColor: string;
  alerts: Alert[];
  onDelete: (id: number) => void;
  onDismiss: (id: number) => void;
  onToggle: (a: Alert) => void;
  editId: number | null;
  editPrice: string;
  setEditId: (id: number | null) => void;
  setEditPrice: (p: string) => void;
  onSaveEdit: (id: number) => void;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-3 border-b border-border flex items-center gap-2">
        <span className={clsx("text-xs font-semibold uppercase tracking-widest label", titleColor)}>{title}</span>
        <span className="pill bg-raised text-muted text-[10px]">{alerts.length}</span>
      </div>
      <table className="w-full text-sm">
        <thead className="border-b border-border text-muted">
          <tr className="[&>th]:px-5 [&>th]:py-2.5 [&>th]:text-left [&>th]:label">
            <th>Stock</th>
            <th>Condition</th>
            <th className="!text-right">Target</th>
            <th></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {alerts.map(a => (
            <tr key={a.id} className="[&>td]:px-5 [&>td]:py-3 hover:bg-raised/40">
              <td>
                <a href={`/stock/${a.ticker}`} className="font-medium hover:text-saffron">
                  {a.ticker.replace(".NS", "")}
                </a>
                <div className="text-xs text-muted truncate max-w-[160px]">{a.company_name}</div>
                {a.triggered_at && (
                  <div className="flex items-center gap-1 text-[10px] text-up mt-0.5">
                    <CheckCircle2 className="h-3 w-3" />
                    Triggered {new Date(a.triggered_at).toLocaleString("en-IN", { timeStyle: "short", dateStyle: "short" })}
                  </div>
                )}
              </td>
              <td>
                <span className={clsx(
                  "pill text-xs",
                  a.alert_type === "above" ? "bg-up/10 text-up" : "bg-down/10 text-down"
                )}>
                  {a.alert_type === "above" ? "↑ Above" : "↓ Below"}
                </span>
              </td>
              <td className="nums text-right">
                {editId === a.id ? (
                  <span className="flex items-center gap-1 justify-end">
                    <input
                      type="number"
                      value={editPrice}
                      onChange={e => setEditPrice(e.target.value)}
                      className="input w-24 text-right text-sm py-1"
                      autoFocus
                    />
                    <button onClick={() => onSaveEdit(a.id)} className="btn-ghost py-1 px-2 text-xs text-up">Save</button>
                    <button onClick={() => setEditId(null)} className="btn-ghost py-1 px-2 text-xs text-muted">✕</button>
                  </span>
                ) : (
                  inr(a.target_price)
                )}
              </td>
              <td>
                <div className="flex items-center gap-1 justify-end">
                  {a.triggered_at ? (
                    <button onClick={() => onDismiss(a.id)} className="btn-ghost py-1 px-2 text-xs text-muted" title="Dismiss">
                      Dismiss
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => { setEditId(a.id); setEditPrice(String(a.target_price)); }}
                        className="btn-ghost p-1.5 text-muted"
                        title="Edit target"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => onToggle(a)}
                        className="btn-ghost p-1.5 text-muted"
                        title={a.is_active ? "Pause" : "Resume"}
                      >
                        {a.is_active ? <BellOff className="h-3.5 w-3.5" /> : <Bell className="h-3.5 w-3.5" />}
                      </button>
                    </>
                  )}
                  <button onClick={() => onDelete(a.id)} className="btn-ghost p-1.5 text-muted hover:text-down" title="Delete">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
