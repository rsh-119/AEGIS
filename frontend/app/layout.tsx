import type { Metadata } from "next";
import { Inter, IBM_Plex_Mono, Fraunces } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { MarketBar } from "@/components/MarketBar";
import { Footer } from "@/components/Footer";
import { ScrollToTop } from "@/components/ScrollToTop";
import { ScrollProgress } from "@/components/motion";
import { SWRCacheProvider } from "@/lib/swr-config";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/ui/toast";
import { ConfirmProvider } from "@/components/ui/confirm-dialog";

// Inter at 300 + 400 — closest open-source analogue to Sohne thin
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: ["300", "400", "500", "600"],
});
const ibmMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  weight: ["400", "500"],
});
// Display face for headlines/wordmarks — high-contrast serif against the
// Inter body for the premium/editorial fintech contrast
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "AEGIS — Indian Market Intelligence",
  description: "AI-powered analysis, forecasts and health checks for NSE & BSE stocks.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${ibmMono.variable} ${fraunces.variable}`}>
      <body suppressHydrationWarning>
        {/*
          Anti-flash: runs before body renders, sets .dark on <html> from
          localStorage so the first paint already has the right theme.
          suppressHydrationWarning on <body> prevents React mismatch warnings
          from the script tag mutating the DOM before hydration.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('aegis-theme')||(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.classList.toggle('dark',t==='dark');}catch(e){}`,
          }}
        />
        <ScrollProgress />
        <AuthProvider>
          <SWRCacheProvider>
            <ToastProvider>
              <ConfirmProvider>
                <ScrollToTop />
                <Nav />
                <MarketBar />
                <main className="px-4 py-5 sm:px-6 md:px-10 lg:px-14" style={{ overflowAnchor: "none" }}>{children}</main>
                <Footer />
              </ConfirmProvider>
            </ToastProvider>
          </SWRCacheProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
