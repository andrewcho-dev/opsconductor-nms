FROM node:20-alpine
WORKDIR /app

# Install dependencies
COPY package.json ./
RUN npm install --no-audit --no-fund

# Set API base for Vite at build time so import.meta.env.VITE_API_BASE is correct
ENV VITE_API_BASE=http://10.120.0.18:8080

# Copy source and build a production bundle
COPY . .
RUN npm run build

# Serve the built app using Vite preview on port 3000
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "3000"]
