# Blindgrasp UI (Next.js standalone). Served behind Caddy on the same origin as the sim server,
# so NEXT_PUBLIC_SIM_URL is empty and the browser calls /state, /action, /stream on the same host.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_SIM_URL=""
ENV NEXT_PUBLIC_SIM_URL=$NEXT_PUBLIC_SIM_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
