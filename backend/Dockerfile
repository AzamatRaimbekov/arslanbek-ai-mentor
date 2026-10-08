FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY railway ./railway
COPY supabase ./supabase
ENV NODE_ENV=production
USER node
CMD ["node", "railway/server.mjs"]
