"""
Aggregation Service — implementación completa (Paso 7)

Flujo por operación:
  1. Recibir AggregateRequest via gRPC
  2. Pedir registros al Storage Service (storage_client)
  3. Distribuir entre workers MPI (aggregator)
  4. Reducir resultados parciales
  5. Retornar AggregateResponse

Operaciones soportadas:
  COUNT      → scalar (float)
  SUM(col)   → scalar (float)
  AVG(col)   → scalar (float)
  DISTINCT   → lista de dicts [{col: val}, ...]
  INNER_JOIN → lista de dicts (registros unidos)

CMD del contenedor:
  python -m mpi4py.futures main.py
  → mpi4py levanta N workers automáticamente al inicio.
  → Si MPI no está disponible, aggregator cae a ProcessPoolExecutor.
"""
import logging
import os
from concurrent import futures as cf

import grpc
from google.protobuf.struct_pb2 import Struct

import aggregation_pb2
import aggregation_pb2_grpc
import aggregator
import storage_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [aggregation] %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


# ── Helper: dict → Struct ──────────────────────────────────────────

def _to_struct(d: dict) -> Struct:
    s = Struct()
    s.update({k: ("" if v is None else v) for k, v in d.items()})
    return s


# ── Servicer ───────────────────────────────────────────────────────

class AggregationServicer(aggregation_pb2_grpc.AggregationServiceServicer):

    def Aggregate(
        self,
        request: aggregation_pb2.AggregateRequest,
        context,
    ) -> aggregation_pb2.AggregateResponse:

        db_name    = request.db_name
        table_name = request.table_name
        operation  = request.operation
        field      = request.field
        filter_d   = {}   # TODO: deserializar request.filter si se necesita

        log.info(
            f"Aggregate op={aggregation_pb2.AggregateOp.Name(operation)} "
            f"db={db_name} table={table_name} field='{field}'"
        )

        # ── 1. Obtener registros del Storage Service ───────────────
        ok, msg, records = storage_client.fetch_records(db_name, table_name, filter_d)
        if not ok:
            return aggregation_pb2.AggregateResponse(success=False, message=msg)

        log.info(f"  Records obtenidos: {len(records)}")

        # ── 2. Despachar al worker MPI según operación ─────────────

        try:
            # COUNT ─────────────────────────────────────────────────
            if operation == aggregation_pb2.COUNT:
                result = aggregator.count(records)
                return aggregation_pb2.AggregateResponse(
                    success=True,
                    scalar_result=result,
                    message=f"COUNT = {int(result)}",
                )

            # SUM ───────────────────────────────────────────────────
            if operation == aggregation_pb2.SUM:
                if not field:
                    return aggregation_pb2.AggregateResponse(
                        success=False, message="SUM requiere un campo (field)"
                    )
                result = aggregator.aggregate_sum(records, field)
                return aggregation_pb2.AggregateResponse(
                    success=True,
                    scalar_result=result,
                    message=f"SUM({field}) = {result}",
                )

            # AVG ───────────────────────────────────────────────────
            if operation == aggregation_pb2.AVG:
                if not field:
                    return aggregation_pb2.AggregateResponse(
                        success=False, message="AVG requiere un campo (field)"
                    )
                result = aggregator.avg(records, field)
                return aggregation_pb2.AggregateResponse(
                    success=True,
                    scalar_result=result,
                    message=f"AVG({field}) = {result:.4f}",
                )

            # DISTINCT ──────────────────────────────────────────────
            if operation == aggregation_pb2.DISTINCT:
                if not field:
                    return aggregation_pb2.AggregateResponse(
                        success=False, message="DISTINCT requiere un campo (field)"
                    )
                rows = aggregator.distinct(records, field)
                structs = [_to_struct(r) for r in rows]
                return aggregation_pb2.AggregateResponse(
                    success=True,
                    rows=structs,
                    message=f"DISTINCT {field} → {len(rows)} valores únicos",
                )

            # INNER JOIN ────────────────────────────────────────────
            if operation == aggregation_pb2.INNER_JOIN:
                join_cfg = request.join
                if not join_cfg.right_table:
                    return aggregation_pb2.AggregateResponse(
                        success=False, message="INNER JOIN requiere join.right_table"
                    )

                right_db = join_cfg.right_db or db_name
                log.info(
                    f"  JOIN {db_name}.{table_name} ← {right_db}.{join_cfg.right_table} "
                    f"ON {join_cfg.left_key} = {join_cfg.right_key}"
                )

                # Obtener tabla derecha
                ok2, msg2, right_records = storage_client.fetch_records(
                    right_db, join_cfg.right_table, {}
                )
                if not ok2:
                    return aggregation_pb2.AggregateResponse(success=False, message=msg2)

                log.info(f"  Right records: {len(right_records)}")

                joined = aggregator.inner_join(
                    records,
                    right_records,
                    join_cfg.left_key,
                    join_cfg.right_key,
                )
                structs = [_to_struct(r) for r in joined]
                return aggregation_pb2.AggregateResponse(
                    success=True,
                    rows=structs,
                    message=f"INNER JOIN → {len(joined)} registros",
                )

            return aggregation_pb2.AggregateResponse(
                success=False,
                message=f"Operación no reconocida: {operation}",
            )

        except Exception as exc:
            log.error(f"Aggregation error: {exc}", exc_info=True)
            return aggregation_pb2.AggregateResponse(success=False, message=str(exc))


import rabbitmq_consumer

# ── Server ─────────────────────────────────────────────────────────

def serve() -> None:
    storage_client.init_client()
    aggregator.init_pool()

    # Arrancar consumer RabbitMQ en background (Paso 8)
    rabbitmq_consumer.start_in_background()

    port = os.getenv("GRPC_PORT", "50055")
    server = grpc.server(
        cf.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length",    32 * 1024 * 1024),
            ("grpc.max_receive_message_length", 32 * 1024 * 1024),
        ],
    )
    aggregation_pb2_grpc.add_AggregationServiceServicer_to_server(
        AggregationServicer(), server
    )
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info(f"✅ Aggregation Service escuchando en puerto {port}")

    try:
        server.wait_for_termination()
    finally:
        storage_client.close_client()
        aggregator.shutdown_pool()


if __name__ == "__main__":
    serve()
