"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LoginPrompt } from "@/components/LoginPrompt";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, ShieldAlert, Users, Eye, Bell, Wallet } from "lucide-react";
import clsx from "clsx";

type AdminUser = {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
  holdings_count: number;
  watchlist_count: number;
  alerts_count: number;
};

type Stats = {
  total_users: number;
  active_users: number;
  total_holdings: number;
  total_watchlist_items: number;
  total_alerts: number;
};

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  return (
    <Card className="flex items-center gap-3 p-4">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-saffron/10 text-saffron ring-1 ring-saffron/20">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</p>
        <p className="nums text-xl font-bold text-fg">{value}</p>
      </div>
    </Card>
  );
}

export default function AdminPage() {
  const { user, isLoading: authLoading } = useAuth();
  const [q, setQ] = useState("");

  const gated = !authLoading && (!user || !user.is_admin);

  const { data: stats } = useSWR<Stats>(user?.is_admin ? "/api/admin/stats" : null, fetcher, {
    revalidateOnFocus: false,
  });
  const { data, isLoading, error } = useSWR<{ users: AdminUser[] }>(
    user?.is_admin ? "/api/admin/users" : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  const users = data?.users ?? [];
  const filtered = q.trim()
    ? users.filter(
        (u) =>
          u.email.toLowerCase().includes(q.toLowerCase()) ||
          u.username.toLowerCase().includes(q.toLowerCase())
      )
    : users;

  if (authLoading) return <div className="skeleton h-64 rounded-2xl" />;

  if (!user) return <LoginPrompt what="the admin dashboard" />;

  if (gated) {
    return (
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <ShieldAlert className="h-8 w-8 text-down" />
        <div>
          <p className="font-semibold">Not authorized</p>
          <p className="mt-1 text-sm text-muted">This account doesn't have admin access.</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-6 animate-fade-up">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-saffron">Internal</p>
        <h1 className="font-display mt-1 text-3xl font-bold">Admin Dashboard</h1>
        <p className="mt-1 text-sm text-muted">All registered users and account activity</p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <StatCard icon={<Users className="h-4 w-4" />} label="Total Users" value={stats.total_users} />
          <StatCard icon={<Users className="h-4 w-4" />} label="Active" value={stats.active_users} />
          <StatCard icon={<Wallet className="h-4 w-4" />} label="Holdings" value={stats.total_holdings} />
          <StatCard icon={<Eye className="h-4 w-4" />} label="Watchlist Items" value={stats.total_watchlist_items} />
          <StatCard icon={<Bell className="h-4 w-4" />} label="Alerts" value={stats.total_alerts} />
        </div>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-raised/40 px-5 py-3">
          <span className="text-sm font-semibold">
            Users {data && <span className="text-muted font-normal">({filtered.length})</span>}
          </span>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search email or username…"
              className="w-56 rounded-lg bg-surface py-1.5 pl-8 pr-3 text-xs ring-1 ring-border outline-none focus:ring-saffron/50"
            />
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skeleton h-12 rounded-lg" style={{ opacity: 1 - i * 0.15 }} />
            ))}
          </div>
        ) : error ? (
          <p className="p-8 text-center text-sm text-muted">Could not load users.</p>
        ) : filtered.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted">No users match "{q}".</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-raised/20 text-[11px] font-medium uppercase tracking-wider text-muted">
                  <th className="px-4 py-3 text-left">User</th>
                  <th className="px-4 py-3 text-left">Email</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-right">Holdings</th>
                  <th className="px-4 py-3 text-right">Watchlist</th>
                  <th className="px-4 py-3 text-right">Alerts</th>
                  <th className="px-4 py-3 text-right">Joined</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((u) => (
                  <tr key={u.id} className="hover:bg-raised/40 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-fg">{u.username}</span>
                        {u.is_admin && (
                          <Badge className="bg-saffron/10 text-saffron ring-1 ring-saffron/20 text-[10px]">Admin</Badge>
                        )}
                      </div>
                      <p className="text-[10px] text-muted">#{u.id}</p>
                    </td>
                    <td className="px-4 py-3 text-muted">{u.email}</td>
                    <td className="px-4 py-3 text-center">
                      <Badge
                        className={clsx(
                          "text-[10px]",
                          u.is_active ? "bg-up/10 text-up ring-1 ring-up/20" : "bg-down/10 text-down ring-1 ring-down/20"
                        )}
                      >
                        {u.is_active ? "Active" : "Disabled"}
                      </Badge>
                    </td>
                    <td className="nums px-4 py-3 text-right">{u.holdings_count}</td>
                    <td className="nums px-4 py-3 text-right">{u.watchlist_count}</td>
                    <td className="nums px-4 py-3 text-right">{u.alerts_count}</td>
                    <td className="px-4 py-3 text-right text-xs text-muted">
                      {new Date(u.created_at).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
