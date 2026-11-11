FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app/src PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config ./config
COPY sql ./sql
COPY src ./src

# data/ and docs/images are mounted as volumes so the warehouse survives the container
VOLUME ["/app/data", "/app/docs/images"]

ENTRYPOINT ["python", "-m", "pipeline"]
CMD ["run"]
