import { AlertTriangle, CheckCircle2, Activity, ShieldAlert } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";

type Health = {
  status?: string;
  status_reason?: string;
  financial_health_score?: number;
  concerns?: string[];
  positives?: string[];
  red_flags?: string[];
  summary?: string;
  error?: string;
};

const STATUS_STYLE: Record<string, string> = {
  Healthy: "text-up ring-up/30 bg-up/10",
  Stable: "text-saffron ring-saffron/30 bg-saffron/10",
  "Under pressure": "text-down ring-down/30 bg-down/10",
  Distressed: "text-down ring-down/40 bg-down/15",
};

function ScoreDot({ score }: { score: number }) {
  const color = score >= 7 ? "bg-up" : score >= 5 ? "bg-saffron" : "bg-down";
  const label = score >= 7 ? "text-up" : score >= 5 ? "text-saffron" : "text-down";
  return (
    <div className="flex items-center gap-1.5">
      {Array.from({ length: 10 }).map((_, i) => (
        <span
          key={i}
          className={`h-2 rounded-full transition-all ${i < score ? `${color} w-4` : "bg-border w-2"}`}
        />
      ))}
      <span className={`nums ml-1 text-sm font-bold ${label}`}>{score}/10</span>
    </div>
  );
}

export function HealthCard({ health }: { health: Health }) {
  if (health?.error) {
    return (
      <Card className="p-5">
        <h3 className="mb-1 font-medium">Company Health</h3>
        <p className="text-sm text-muted">{health.error}</p>
      </Card>
    );
  }

  const status = health?.status || "Unknown";
  const style = STATUS_STYLE[status] || "text-muted ring-border bg-raised";

  return (
    <Card className="p-5 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <h3 className="flex items-center gap-2 font-medium">
          <Activity className="h-4 w-4 text-saffron" /> Company Health
        </h3>
        <Badge className={`ring-1 ${style}`}>{status}</Badge>
      </div>

      {/* Health score */}
      {typeof health?.financial_health_score === "number" && (
        <div>
          <Label className="mb-2 block">Health Score</Label>
          <ScoreDot score={health.financial_health_score} />
          {health?.status_reason && (
            <p className="mt-2 text-xs text-muted">{health.status_reason}</p>
          )}
        </div>
      )}

      {/* Summary */}
      {health?.summary && (
        <p className="text-sm leading-relaxed text-fg/90">{health.summary}</p>
      )}

      {/* Red flags — critical issues only */}
      {health?.red_flags && health.red_flags.length > 0 && (
        <div className="rounded-xl border border-down/30 bg-down/5 p-3.5">
          <Label className="mb-2.5 flex items-center gap-1.5 text-down">
            <ShieldAlert className="h-3.5 w-3.5" /> Red Flags
          </Label>
          <ul className="space-y-1.5">
            {health.red_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm font-medium text-down/90">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-down" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Concerns & Positives */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label className="mb-2 flex items-center gap-1.5 text-down">
            <AlertTriangle className="h-3.5 w-3.5" /> Concerns
          </Label>
          <ul className="space-y-2">
            {(health?.concerns?.length ? health.concerns : ["None flagged"]).map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-fg/80">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-down/60" />
                {c}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <Label className="mb-2 flex items-center gap-1.5 text-up">
            <CheckCircle2 className="h-3.5 w-3.5" /> Positives
          </Label>
          <ul className="space-y-2">
            {(health?.positives?.length ? health.positives : ["None flagged"]).map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-fg/80">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-up/60" />
                {p}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}
