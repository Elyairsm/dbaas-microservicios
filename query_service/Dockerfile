FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY proto/ /proto/
COPY query_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m grpc_tools.protoc \
    -I/proto \
    --python_out=. \
    --grpc_python_out=. \
    /proto/auth.proto \
    /proto/storage.proto \
    /proto/query.proto \
    /proto/aggregation.proto

COPY query_service/ .

EXPOSE 50054
CMD ["python", "main.py"]
