FROM node:20-alpine
WORKDIR /app

# Install dependencies
COPY package.json ./
RUN npm install --no-audit --no-fund

# Install serve for static file serving
RUN npm install --save-dev serve

# Set API base for Vite at build time so import.meta.env.VITE_API_BASE is correct
ENV VITE_API_BASE=http://10.120.0.18:8000

# Copy source and build a production bundle
COPY . .
RUN npm run build

# Serve the built app using serve (handles SPA routing)
CMD ["npx", "serve", "-s", "dist", "-l", "3000"]
