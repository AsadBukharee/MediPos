FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# NEXT_PUBLIC_* values are compiled into the bundle, so they are build arguments.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_CURRENCY=PKR
ARG NEXT_PUBLIC_BUSINESS_NAME="MediPos Pharmacy"
ENV DOCKER_BUILD=1 NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_CURRENCY=$NEXT_PUBLIC_CURRENCY \
    NEXT_PUBLIC_BUSINESS_NAME=$NEXT_PUBLIC_BUSINESS_NAME NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S medipos && adduser -S medipos -G medipos
COPY --from=build --chown=medipos:medipos /app/.next/standalone ./
COPY --from=build --chown=medipos:medipos /app/.next/static ./.next/static
COPY --from=build --chown=medipos:medipos /app/public ./public
USER medipos
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD wget -qO- http://127.0.0.1:3000/login >/dev/null || exit 1
CMD ["node", "server.js"]
