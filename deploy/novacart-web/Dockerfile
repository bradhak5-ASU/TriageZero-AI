# Builds and serves the NovaCart shopfront.
#
# NovaCart's own Dockerfile runs `npm run dev`, Vite's development server. That
# cannot be used here: Vite 5.4.12+ rejects requests whose Host header is not
# localhost, so on Cloud Run every request returns "Blocked request. This host
# is not allowed." Its repository is read-only, so the fix cannot live there -
# this image builds the app properly and serves the static output instead,
# which is what should be deployed regardless.
#
# The application source is copied into ./app by deploy/build-novacart-web.sh;
# nothing in the NovaCart repository is modified.
FROM node:20-alpine AS build
WORKDIR /src
COPY app/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY app/ ./

# Vite compiles these into the bundle at build time, so they are passed as
# build args rather than set on the running container.
ARG VITE_API_BASE_URL
ARG VITE_NOVACART_DEFECT_SCENARIO=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_NOVACART_DEFECT_SCENARIO=$VITE_NOVACART_DEFECT_SCENARIO
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
ENV PORT=8080
EXPOSE 8080
