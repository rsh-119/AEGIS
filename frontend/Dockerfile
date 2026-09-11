# ── Build stage ───────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Where the Next.js /api/* rewrite proxies to, server-side. Build-time on
# purpose: Next evaluates rewrites() during `next build` and freezes the
# destination into .next/routes-manifest.json, so passing this at container
# runtime has no effect whatsoever.
#
# This is NOT a browser-visible value, which is why it is no longer called
# NEXT_PUBLIC_*. The browser only ever talks to this container's own origin —
# the backend's session cookies are SameSite=Strict and would be dropped on a
# cross-site request. NEXT_PUBLIC_API_URL is still honoured as a fallback (see
# next.config.js) so existing Vercel/Render builds keep working unchanged.
ARG API_PROXY_TARGET=http://backend:8000
ENV API_PROXY_TARGET=$API_PROXY_TARGET

RUN npm run build


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS runtime

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

WORKDIR /app

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
