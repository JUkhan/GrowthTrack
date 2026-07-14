# Multi-stage: build the React SPA, then serve it (plus proxy to api/) via
# a pinned Nginx (>=1.30.1 stable / >=1.31.0 mainline — CVE-2026-42945).
FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM nginx:1.30.3-alpine
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=web-build /web/dist /usr/share/nginx/html
