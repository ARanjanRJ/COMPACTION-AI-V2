FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY static ./static
RUN useradd -m app && chown -R app /app
USER app
ENV HOST=0.0.0.0 PORT=5000
EXPOSE 5000
# HOST=0.0.0.0 inside a container requires COMPACTION_ACCESS_TOKEN (startup refuses otherwise).
# gunicorn: threads (not workers) so rate-limit/concurrency state is shared in one process.
CMD ["gunicorn", "--chdir", "backend", "--workers", "1", "--threads", "8", "--timeout", "0", "--bind", "0.0.0.0:5000", "app:app"]
