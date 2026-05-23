FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY proto/ /proto/
COPY storage_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m grpc_tools.protoc \
    -I/proto \
    --python_out=. \
    --grpc_python_out=. \
    /proto/storage.proto

COPY storage_service/ .

RUN mkdir -p /app/data
EXPOSE 50053
CMD ["python", "main.py"]
