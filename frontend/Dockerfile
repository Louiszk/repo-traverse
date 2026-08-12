# Stage 1: Base & Dependencies
FROM node:22-alpine AS base
WORKDIR /app
COPY package.json package-lock.json ./
RUN apk add --no-cache gettext
RUN --mount=type=cache,target=/root/.npm npm ci

# Stage 2: Local Development (HMR & Dev Server)
FROM base AS dev
ARG VITE_MAX_MESSAGES_PER_SESSION
ENV VITE_MAX_MESSAGES_PER_SESSION=$VITE_MAX_MESSAGES_PER_SESSION
ARG VITE_MAX_CHAT_MESSAGE_LENGTH
ENV VITE_MAX_CHAT_MESSAGE_LENGTH=$VITE_MAX_CHAT_MESSAGE_LENGTH
COPY . .
RUN chmod +x /app/docker-entrypoint.sh
ENV IMPRINT_TEMPLATE_PATH=/app/impressum.html.template
ENV IMPRINT_OUTPUT_PATH=/app/public/impressum.html
EXPOSE 5173
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Stage 3: Production Build
FROM base AS build
ARG VITE_MAX_MESSAGES_PER_SESSION
ENV VITE_MAX_MESSAGES_PER_SESSION=$VITE_MAX_MESSAGES_PER_SESSION
ARG VITE_MAX_CHAT_MESSAGE_LENGTH
ENV VITE_MAX_CHAT_MESSAGE_LENGTH=$VITE_MAX_CHAT_MESSAGE_LENGTH
COPY . .
RUN npm run build

# Stage 4: Production Serve (Lightweight Unprivileged Nginx)
FROM nginxinc/nginx-unprivileged:1.26-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app/impressum.html.template /etc/repotraverse/impressum.html.template
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
USER root
RUN apk add --no-cache gettext \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chown -R nginx:nginx /usr/share/nginx/html

ENV IMPRINT_TEMPLATE_PATH=/etc/repotraverse/impressum.html.template
ENV IMPRINT_OUTPUT_PATH=/usr/share/nginx/html/impressum.html
RUN echo 'server { \
    listen 5173; \
    server_name _; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
    }' > /etc/nginx/conf.d/default.conf
USER nginx
EXPOSE 5173
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
