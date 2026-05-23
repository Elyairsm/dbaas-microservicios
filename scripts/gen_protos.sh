#!/usr/bin/env bash
# gen_protos.sh — regenera los stubs gRPC de todos los servicios
# Uso: bash scripts/gen_protos.sh   (desde la raíz del proyecto)
set -e

PROTO_DIR="./proto"

declare -A SERVICE_PROTOS=(
  ["auth_service"]="auth.proto"
  ["admin_service"]="auth.proto admin.proto storage.proto"
  ["storage_service"]="storage.proto"
  ["query_service"]="auth.proto storage.proto query.proto aggregation.proto"
  ["aggregation_service"]="storage.proto aggregation.proto"
  ["gateway"]="auth.proto admin.proto query.proto"
)

for service in "${!SERVICE_PROTOS[@]}"; do
  echo "▶ Generando stubs para $service..."
  protos="${SERVICE_PROTOS[$service]}"
  proto_files=""
  for p in $protos; do
    proto_files="$proto_files $PROTO_DIR/$p"
  done
  python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="./$service" \
    --grpc_python_out="./$service" \
    $proto_files
  echo "  ✓ $service"
done

echo ""
echo "✅ Todos los stubs generados."
