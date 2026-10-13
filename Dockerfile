FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# BACKEND_URL: /api/* proxy-ийн чиглэл (rewrites build үед тогтоно). NEXT_PUBLIC_*: browser-ийн кодонд шигдэнэ (зөвхөн public утга)
ARG BACKEND_URL
ARG NEXT_PUBLIC_WS_URL
ENV BACKEND_URL=$BACKEND_URL NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
