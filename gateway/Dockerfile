FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY proto/ /proto/
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m grpc_tools.protoc \
    -I/proto \
    --python_out=. \
    --grpc_python_out=. \
    /proto/auth.proto \
    /proto/admin.proto \
    /proto/query.proto

COPY gateway/ .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
