import { ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";

export type SortDir = "asc" | "desc" | null;

export function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active || dir === null) return <ArrowUpDown className="h-3 w-3 shrink-0 text-muted/40" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 shrink-0 text-saffron" />
    : <ArrowDown className="h-3 w-3 shrink-0 text-saffron" />;
}
