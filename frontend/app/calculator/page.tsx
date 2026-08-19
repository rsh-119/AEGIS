import { Calculator } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ProjectionCalculator } from "@/components/ProjectionCalculator";

export default function CalculatorPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 animate-fade-up">
      <div>
        <PageHeader />
        <p className="mt-2 pl-[46px] text-sm text-muted">
          Project a monthly SIP or one-time investment forward at an assumed annual return —
          works for any investment, not tied to a specific stock. For a real per-stock
          calculator using actual historical prices, open any stock&apos;s page instead.
        </p>
      </div>

      <Card className="p-6">
        <ProjectionCalculator />
      </Card>
    </div>
  );
}

function PageHeader() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-saffron/10 ring-1 ring-saffron/20">
        <Calculator className="h-4 w-4 text-saffron" />
      </div>
      <h1 className="font-display text-2xl font-semibold tracking-tight">Returns Calculator</h1>
    </div>
  );
}
