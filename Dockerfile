# build frontend ก่อน แล้วค่อยเสิร์ฟจาก backend เดียวกัน (เว็บ + API อยู่คนละ stage คนละ image สุดท้าย)
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS backend
WORKDIR /app

# opencv-python-headless ต้องการ libglib2.0-0 แม้ไม่มี GUI
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist ./frontend_dist

ENV BAHT_DATA_DIR=/data
ENV FRONTEND_DIST=/app/frontend_dist
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
