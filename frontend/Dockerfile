# Build context: ai-ops-platform repository root (see docs/DEPLOYMENT.md).
# Example: docker build -f frontend/Dockerfile -t your-registry/kai-frontend:latest .
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend/index.html ./
COPY frontend/scripts ./scripts
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist/index.html /usr/share/nginx/html/index.html
COPY frontend/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
