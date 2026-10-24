# --- 1. build the React app ---
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. Django API + built SPA in one service ---
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput -v 0
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py bootstrap_admin && gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60"]
