# Build static bundle (single-page index.html in dist/)
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY index.html ./
COPY scripts ./scripts
RUN npm run build

# Serve with same routing rules as legacy GitOps nginx ConfigMap
FROM nginx:1.27-alpine
COPY --from=build /app/dist/index.html /usr/share/nginx/html/index.html
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
