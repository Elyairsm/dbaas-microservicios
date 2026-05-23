FROM python:3.11-slim
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Proto files
COPY proto/ /proto/

# Dependencies
COPY auth_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Generate gRPC stubs
RUN python -m grpc_tools.protoc \
    -I/proto \
    --python_out=. \
    --grpc_python_out=. \
    /proto/auth.proto

# Service code
COPY auth_service/ .

EXPOSE 50051
CMD ["python", "main.py"]
