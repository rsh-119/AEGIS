"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SearchBox } from "./SearchBox";
import { Sun, Moon, Menu, X, Bell, LogIn, LogOut, UserCircle } from "lucide-react";
import clsx from "clsx";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { RippleLink } from "@/components/ui/ripple-link";

const links = [
  { href: "/",          label: "Home"      },
  { href: "/market",    label: "Market"    },
  { href: "/mf",        label: "MF & ETF"  },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/alerts",    label: "Alerts"    },
];

export function Nav() {
  const path   = usePathname();
  const router = useRouter();
  const { user, logout, isLoading: authLoading } = useAuth();
  const [dark,       setDark]       = useState(false);
  const [scrolled,   setScrolled]   = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenu,   setUserMenu]   = useState(false);

  // Close mobile menu on route change
  useEffect(() => { setMobileOpen(false); }, [path]);

  useEffect(() => {
    const saved       = localStorage.getItem("aegis-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark      = saved ? saved === "dark" : prefersDark;
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 12);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  // Lock body scroll when mobile menu is open
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("aegis-theme", next ? "dark" : "light");
  }

  return (
    <header
      className={clsx(
        "sticky top-0 z-40 transition-all duration-300",
        scrolled ? "nav-glass shadow-lg" : "border-b border-border/60 bg-ink/60 backdrop-blur-xl"
      )}
    >
      {scrolled && <div className="glow-line absolute top-0 inset-x-0" />}

      {/* ── Main bar ── */}
      <div className="flex h-14 items-center gap-3 px-4 sm:px-6 md:px-10 xl:px-14">

        {/* Logo */}
        <Link href="/" className="group flex shrink-0 items-center gap-2">
          <span className={clsx(
            "grid h-8 w-8 place-items-center transition-all duration-200",
            "drop-shadow-[0_0_10px_rgb(var(--color-saffron)/0.35)] group-hover:drop-shadow-[0_0_16px_rgb(var(--color-saffron)/0.55)]"
          )}>
            <Image src="/aegis-logo.png" alt="AEGIS logo" width={32} height={32} priority className="h-8 w-8 object-contain" />
          </span>
          <div className="flex flex-col leading-none">
            <span className="font-display text-base font-bold tracking-tight text-fg">AEGIS</span>
            <span className="hidden text-[8.5px] font-medium uppercase tracking-[0.12em] text-muted sm:block">
              Equity Intelligence
            </span>
          </div>
        </Link>

        {/* Desktop search — centered in the space actually left between logo and right side */}
        <div className="hidden min-w-0 flex-1 justify-center xl:flex">
          {path !== "/" && (
            <div className="w-full max-w-sm xl:max-w-[400px]">
              <SearchBox />
            </div>
          )}
        </div>

        {/* Right side */}
        <div className="ml-auto flex shrink-0 items-center gap-1 xl:ml-0">

          {/* Desktop nav links */}
          <nav className="hidden xl:flex items-center gap-0.5 text-sm">
            {links.map((l) => {
              const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
              return (
                <RippleLink key={l.href} href={l.href}
                  className={clsx(
                    "rounded-lg px-3 py-1.5 font-medium transition-all duration-150",
                    active ? "text-fg" : "text-muted hover:text-fg"
                  )}
                >
                  {active && <span className="absolute inset-0 rounded-lg bg-raised/80 ring-1 ring-border/60" />}
                  {active && <span className="absolute bottom-0.5 left-1/2 h-0.5 w-3 -translate-x-1/2 rounded-full bg-saffron" />}
                  <span className="relative">{l.label}</span>
                </RippleLink>
              );
            })}
          </nav>

          {/* Live indicator — desktop only */}
          <div className="mx-2 hidden h-4 w-px bg-border/60 xl:block" />
          <div className="hidden items-center gap-1.5 rounded-full border border-up/20 bg-up/8 px-2.5 py-1 xl:flex">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-up" />
            </span>
            <span className="text-[10px] font-semibold text-up">Live</span>
          </div>

          {/* Theme toggle */}
          <button onClick={toggleTheme} aria-label="Toggle theme"
            className="grid h-8 w-8 place-items-center rounded-lg text-muted transition-all duration-150 hover:bg-raised hover:text-fg"
          >
            {dark ? <Sun className="h-[15px] w-[15px]" /> : <Moon className="h-[15px] w-[15px]" />}
          </button>

          {/* Auth — desktop */}
          {!authLoading && (
            <div className="hidden xl:block relative">
              {user ? (
                <>
                  <button
                    onClick={() => setUserMenu(o => !o)}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted hover:text-fg hover:bg-raised transition-all"
                  >
                    <UserCircle className="h-4 w-4" />
                    <span className="max-w-[100px] truncate">{user.username}</span>
                  </button>
                  {userMenu && (
                    <div className="absolute right-0 top-full mt-1 w-44 rounded-xl border border-border bg-ink shadow-xl z-50">
                      <div className="px-3 py-2 border-b border-border">
                        <p className="text-xs text-muted truncate">{user.email}</p>
                      </div>
                      <Link href="/alerts" className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-raised" onClick={() => setUserMenu(false)}>
                        <Bell className="h-3.5 w-3.5" /> Alerts
                      </Link>
                      <button
                        onClick={() => { logout(); setUserMenu(false); router.push("/login"); }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-down hover:bg-raised"
                      >
                        <LogOut className="h-3.5 w-3.5" /> Sign out
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <Button asChild className="flex items-center gap-1.5 text-sm">
                  <Link href="/login"><LogIn className="h-4 w-4" /> Sign in</Link>
                </Button>
              )}
            </div>
          )}

          {/* Hamburger — mobile/tablet only */}
          <button
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Toggle menu"
            className="grid h-8 w-8 place-items-center rounded-lg text-muted transition-all duration-150 hover:bg-raised hover:text-fg xl:hidden"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile search (non-home pages) */}
      {path !== "/" && (
        <div className="px-4 pb-2.5 xl:hidden">
          <SearchBox />
        </div>
      )}

      {/* ── Mobile nav drawer ── */}
      {mobileOpen && (
        <div className="border-t border-border bg-surface xl:hidden">
          <nav className="flex flex-col py-2">
            {links.map((l) => {
              const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
              return (
                <RippleLink key={l.href} href={l.href}
                  className={clsx(
                    "flex items-center gap-3 px-5 py-3.5 text-sm font-medium transition-colors",
                    active
                      ? "bg-saffron/8 text-saffron border-l-2 border-saffron"
                      : "text-muted hover:bg-raised hover:text-fg border-l-2 border-transparent"
                  )}
                >
                  {l.label}
                  {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-saffron" />}
                </RippleLink>
              );
            })}
          </nav>
          {/* Auth actions in mobile menu */}
          <div className="border-t border-border px-5 py-3 space-y-2">
            {user ? (
              <>
                <p className="text-xs text-muted">{user.email}</p>
                <button
                  onClick={() => { logout(); router.push("/login"); setMobileOpen(false); }}
                  className="flex items-center gap-2 text-sm text-down"
                >
                  <LogOut className="h-3.5 w-3.5" /> Sign out
                </button>
              </>
            ) : (
              <Link href="/login" className="flex items-center gap-2 text-sm text-saffron" onClick={() => setMobileOpen(false)}>
                <LogIn className="h-3.5 w-3.5" /> Sign in
              </Link>
            )}
          </div>

          {/* Live indicator in mobile menu */}
          <div className="flex items-center gap-2 border-t border-border px-5 py-3">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-up" />
            </span>
            <span className="text-xs text-up font-medium">NSE / BSE live</span>
          </div>
        </div>
      )}
    </header>
  );
}
