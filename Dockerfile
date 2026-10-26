FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./frontend
COPY config/vite.config.js ./config/vite.config.js
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIGIL_DATA_DIR=/var/data PORT=10000 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home vigil \
    && mkdir -p /var/data && chown vigil:vigil /var/data
COPY config/requirements/web.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY scripts/backup_investigations.py ./scripts/backup_investigations.py
COPY data/bronze/reviews.csv ./data/bronze/reviews.csv
COPY --from=frontend /build/dist ./dist
USER vigil
EXPOSE 10000
CMD ["python", "-m", "backend.serve"]
