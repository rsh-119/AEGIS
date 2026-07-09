import {
  Cpu, Landmark, Heart, Zap, Factory, Layers,
  Radio, Sun, Home as HomeIcon, ShoppingCart, ArrowUpRight,
  type LucideIcon,
} from "lucide-react";

export type SectorCfg = {
  name: string;
  slug: string;           // API sector name
  indexSlug?: string;     // /api/market/index/{indexSlug}
  icon: LucideIcon;
  color: string;          // tailwind bg + text combo
  accent: string;         // border / ring color
};

export const SECTORS: SectorCfg[] = [
  { name: "Technology",           slug: "Technology",           indexSlug: "niftyit",      icon: Cpu,         color: "bg-blue-500/10 text-blue-500",      accent: "border-blue-500/30 ring-blue-500/20" },
  { name: "Financial Services",   slug: "Financial Services",   indexSlug: "banknifty",    icon: Landmark,    color: "bg-emerald-500/10 text-emerald-500", accent: "border-emerald-500/30 ring-emerald-500/20" },
  { name: "Healthcare",           slug: "Healthcare",           indexSlug: "niftypharma",  icon: Heart,       color: "bg-rose-500/10 text-rose-500",       accent: "border-rose-500/30 ring-rose-500/20" },
  { name: "Energy",               slug: "Energy",               indexSlug: "niftyenergy",  icon: Zap,         color: "bg-orange-500/10 text-orange-500",   accent: "border-orange-500/30 ring-orange-500/20" },
  { name: "Consumer Defensive",   slug: "Consumer Defensive",   indexSlug: "niftyfmcg",   icon: ShoppingCart,color: "bg-purple-500/10 text-purple-500",   accent: "border-purple-500/30 ring-purple-500/20" },
  { name: "Consumer Cyclical",    slug: "Consumer Cyclical",    indexSlug: "niftyauto",    icon: ArrowUpRight,color: "bg-pink-500/10 text-pink-500",        accent: "border-pink-500/30 ring-pink-500/20" },
  { name: "Industrials",          slug: "Industrials",          indexSlug: "niftyinfra",   icon: Factory,     color: "bg-yellow-500/10 text-yellow-600",   accent: "border-yellow-500/30 ring-yellow-500/20" },
  { name: "Basic Materials",      slug: "Basic Materials",      indexSlug: "niftymetal",   icon: Layers,      color: "bg-stone-500/10 text-stone-500",     accent: "border-stone-500/30 ring-stone-500/20" },
  { name: "Real Estate",          slug: "Real Estate",          indexSlug: "niftyrealty",  icon: HomeIcon,    color: "bg-teal-500/10 text-teal-500",       accent: "border-teal-500/30 ring-teal-500/20" },
  { name: "Communication",        slug: "Communication Services",indexSlug: "niftymedia",  icon: Radio,       color: "bg-indigo-500/10 text-indigo-500",   accent: "border-indigo-500/30 ring-indigo-500/20" },
];

export function findSectorCfg(sector: string): SectorCfg | undefined {
  const lo = sector.trim().toLowerCase();
  return SECTORS.find((s) => s.slug.toLowerCase() === lo || s.name.toLowerCase() === lo);
}
