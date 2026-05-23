FROM python:3.11-slim
WORKDIR /app

# OpenMPI para mpi4py
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libopenmpi-dev \
    openmpi-bin \
    && rm -rf /var/lib/apt/lists/*

COPY proto/ /proto/
COPY aggregation_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m grpc_tools.protoc \
    -I/proto \
    --python_out=. \
    --grpc_python_out=. \
    /proto/storage.proto \
    /proto/aggregation.proto

COPY aggregation_service/ .

EXPOSE 50055
# mpirun lanza el proceso principal + N workers automáticamente.
# --allow-run-as-root es necesario porque Docker corre como root por default.
CMD ["mpirun", "--allow-run-as-root", "-n", "1", \
     "python", "-m", "mpi4py.futures", "main.py"]
