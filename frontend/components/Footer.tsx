"use client";

import Link from "next/link";
import { useState } from "react";
import { Github, Twitter, Linkedin, Mail, X, Send } from "lucide-react";
import { Card } from "@/components/ui/card";

const SOCIALS = [
  { icon: Github,   label: "GitHub",   href: "https://github.com/rishabh" },
  { icon: Linkedin, label: "LinkedIn", href: "https://linkedin.com/in/rishabh" },
  { icon: Twitter,  label: "Twitter",  href: "https://twitter.com/rishabh" },
];

function ContactModal({ onClose }: { onClose: () => void }) {
  const [name, setName]       = useState("");
  const [email, setEmail]     = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent]       = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const subject = encodeURIComponent(`[AEGIS] Message from ${name}`);
    const body    = encodeURIComponent(`Name: ${name}\nEmail: ${email}\n\n${message}`);
    window.location.href = `mailto:personalrsh11@gmail.com?subject=${subject}&body=${body}`;
    setSent(true);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <Card className="w-full max-w-md overflow-hidden">
        <div className="flex items-center justify-between border-b border-border bg-raised/40 px-5 py-4">
          <div>
            <h2 className="text-sm font-bold">Contact Us</h2>
            <p className="text-[11px] text-muted mt-0.5">We&apos;ll get back to you via email</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-raised hover:text-fg transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {sent ? (
          <div className="flex flex-col items-center gap-3 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-up/10">
              <Send className="h-5 w-5 text-up" />
            </div>
            <p className="text-sm font-semibold">Opening your email client…</p>
            <p className="text-xs text-muted">Your draft is ready — just hit send!</p>
            <button onClick={onClose} className="mt-2 rounded-lg bg-saffron px-4 py-2 text-xs font-bold text-white hover:bg-saffron/90 transition-colors">
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-5 space-y-4">
            <div className="space-y-1.5">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-muted">Name</label>
              <input
                required value={name} onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full rounded-lg bg-surface px-3 py-2 text-sm text-fg outline-none ring-1 ring-border focus:ring-saffron/50 transition-all"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-muted">Email</label>
              <input
                type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-lg bg-surface px-3 py-2 text-sm text-fg outline-none ring-1 ring-border focus:ring-saffron/50 transition-all"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-muted">Message</label>
              <textarea
                required rows={4} value={message} onChange={(e) => setMessage(e.target.value)}
                placeholder="Your message or feedback…"
                className="w-full resize-none rounded-lg bg-surface px-3 py-2 text-sm text-fg outline-none ring-1 ring-border focus:ring-saffron/50 transition-all"
              />
            </div>
            <button
              type="submit"
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-saffron px-4 py-2.5 text-sm font-bold text-white hover:bg-saffron/90 transition-colors"
            >
              <Send className="h-3.5 w-3.5" />
              Send Message
            </button>
          </form>
        )}
      </Card>
    </div>
  );
}

export function Footer() {
  const [showContact, setShowContact] = useState(false);

  return (
    <>
      <footer className="relative border-t border-border/60 bg-ink/40 backdrop-blur-sm">
        {/* Top glow line */}
        <div className="glow-line absolute top-0 inset-x-0 opacity-60" />
        <div className="mx-auto max-w-screen-xl px-6 py-8 md:px-12 lg:px-16">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3 md:items-center">
            {/* Left: Brand block — flush left with slight inset */}
            <div className="space-y-2 pl-0">
              <div className="flex items-center gap-2">
                <span className="font-display text-xl font-bold text-saffron drop-shadow-[0_0_12px_rgb(var(--color-saffron)/0.4)]">AEGIS</span>
                <span className="rounded-md border border-saffron/20 bg-saffron/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-saffron">
                  Beta
                </span>
              </div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted/70">
                Advanced Equity Guidance and Intelligent System
              </p>
              <p className="text-sm text-muted">
                Data via Yahoo Finance &middot; For information only, not investment advice.
              </p>
            </div>

            {/* Center: Built with heart — truly centered in the 3-col grid */}
            <div className="flex flex-col items-center justify-center text-center">
              <p className="text-base font-semibold text-fg/80">
                Built with <span className="text-red-400">&#9829;</span> by Rishabh
              </p>
            </div>

            {/* Right: Links */}
            <div className="flex justify-end gap-10">
              <div className="space-y-2">
                <p className="text-xs font-bold uppercase tracking-wider text-muted">Navigate</p>
                {[
                  { label: "Home",            href: "/"       },
                  { label: "Peer Comparison", href: "/peers"  },
                  { label: "Market",          href: "/market" },
                ].map((l) => (
                  <Link key={l.href} href={l.href}
                    className="block text-sm text-muted hover:text-fg transition-colors">
                    {l.label}
                  </Link>
                ))}
              </div>

              <div className="space-y-2">
                <p className="text-xs font-bold uppercase tracking-wider text-muted">Connect</p>
                {SOCIALS.map(({ icon: Icon, label, href }) => (
                  <a key={label} href={href} target="_blank" rel="noreferrer"
                    className="flex items-center gap-2 text-sm text-muted hover:text-fg transition-colors">
                    <Icon className="h-4 w-4" />
                    {label}
                  </a>
                ))}
                <button
                  onClick={() => setShowContact(true)}
                  className="flex items-center gap-2 text-sm text-muted hover:text-fg transition-colors">
                  <Mail className="h-4 w-4" />
                  Contact Us
                </button>
              </div>
            </div>
          </div>

          <div className="mt-6 border-t border-border/60 pt-4 text-center">
            <p className="text-xs text-muted/50">
              &copy; {new Date().getFullYear()} AEGIS. All rights reserved.
            </p>
          </div>
        </div>
      </footer>

      {showContact && <ContactModal onClose={() => setShowContact(false)} />}
    </>
  );
}
