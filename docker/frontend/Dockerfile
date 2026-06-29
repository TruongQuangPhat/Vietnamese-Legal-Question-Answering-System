FROM node:22-alpine AS deps

WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY apps/frontend/package.json apps/frontend/package-lock.json ./

RUN npm ci

FROM node:22-alpine AS build

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY apps/frontend ./

RUN npm run build

FROM node:22-alpine AS runner

WORKDIR /app

ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NODE_ENV=production \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci --omit=dev

COPY --from=build /app/.next ./.next

EXPOSE 3000

CMD ["npm", "run", "start"]
