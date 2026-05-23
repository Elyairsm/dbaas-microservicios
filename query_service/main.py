"""
Query Service — implementación completa (Paso 6)

Dos interfaces de entrada:
  ExecuteSQL   → parsea SQL con sqlglot → despacha a Storage o Aggregation
  ExecuteNoSQL → opera directamente sobre el payload JSON

Routing:
  CRUD (insert/find/update/delete) → Storage Service (gRPC directo)
  Agregaciones (COUNT/SUM/AVG/DISTINCT/JOIN) → Aggregation Service (gRPC)

Nota: RabbitMQ se integra en Paso 8 para el despacho async de agregaciones.
"""
import logging
import os
from concurrent import futures

import grpc
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

import query_pb2
import query_pb2_grpc
import storage_pb2
import aggregation_pb2
import grpc_clients
from sql_parser import parse_sql

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [query] %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)


# ── Conversores Protobuf ↔ Python ──────────────────────────────────

def _to_struct(d: dict) -> Struct:
    s = Struct()
    s.update({k: ("" if v is None else v) for k, v in d.items()})
    return s


def _from_struct(s: Struct) -> dict:
    return json_format.MessageToDict(s) if s and s.fields else {}


def _structs_to_rows(structs) -> list[dict]:
    return [json_format.MessageToDict(s) for s in structs]


# ── Dispatcher: operación dict → llamada gRPC ─────────────────────

def _dispatch(op: dict) -> query_pb2.QueryResponse:
    """
    Recibe un dict de operación normalizado (del sql_parser o del NoSQL handler)
    y llama al servicio correcto via gRPC.
    """
    kind = op["op"]

    # ── CRUD → Storage Service ─────────────────────────────────────
    if kind == "insert":
        resp = grpc_clients.storage_stub().Insert(
            storage_pb2.InsertRequest(
                db_name    = op["db_name"],
                table_name = op["table_name"],
                record     = _to_struct(op.get("record", {})),
            )
        )
        return query_pb2.QueryResponse(
            success=resp.success,
            affected_rows=resp.affected_rows,
            message=resp.message,
        )

    if kind == "find":
        resp = grpc_clients.storage_stub().Find(
            storage_pb2.FindRequest(
                db_name    = op["db_name"],
                table_name = op["table_name"],
                filter     = _to_struct(op.get("filter", {})),
                limit      = op.get("limit",  0),
                offset     = op.get("offset", 0),
            )
        )
        return query_pb2.QueryResponse(
            success=resp.success,
            rows=resp.records,
            affected_rows=len(resp.records),
            message=resp.message,
        )

    if kind == "update":
        resp = grpc_clients.storage_stub().Update(
            storage_pb2.UpdateRequest(
                db_name    = op["db_name"],
                table_name = op["table_name"],
                filter     = _to_struct(op.get("filter",  {})),
                updates    = _to_struct(op.get("updates", {})),
            )
        )
        return query_pb2.QueryResponse(
            success=resp.success,
            affected_rows=resp.affected_rows,
            message=resp.message,
        )

    if kind == "delete":
        resp = grpc_clients.storage_stub().Delete(
            storage_pb2.DeleteRequest(
                db_name    = op["db_name"],
                table_name = op["table_name"],
                filter     = _to_struct(op.get("filter", {})),
            )
        )
        return query_pb2.QueryResponse(
            success=resp.success,
            affected_rows=resp.affected_rows,
            message=resp.message,
        )

    # ── Agregaciones → RabbitMQ (async) → Aggregation Service ────
    if kind == "aggregate":
        rabbit_request = {
            "db_name":    op["db_name"],
            "table_name": op["table_name"],
            "operation":  op["agg_op"],
            "field":      op.get("agg_field", ""),
            "filter":     op.get("filter", {}),
            "join":       op.get("join"),
        }

        # Intentar RabbitMQ; si no está disponible caer a gRPC directo
        result_dict: dict | None = None
        try:
            import rabbitmq_rpc
            result_dict = rabbitmq_rpc.call(rabbit_request)
            log.info("Aggregation via RabbitMQ ✓")
        except (ConnectionError, TimeoutError) as exc:
            log.warning(f"RabbitMQ no disponible ({exc}), usando gRPC directo")

        # Fallback gRPC ─────────────────────────────────────────────
        if result_dict is None:
            agg_op_map = {
                "COUNT":      aggregation_pb2.COUNT,
                "SUM":        aggregation_pb2.SUM,
                "AVG":        aggregation_pb2.AVG,
                "DISTINCT":   aggregation_pb2.DISTINCT,
                "INNER_JOIN": aggregation_pb2.INNER_JOIN,
            }
            agg_op = agg_op_map.get(op["agg_op"])
            if agg_op is None:
                return query_pb2.QueryResponse(
                    success=False,
                    message=f"Operación de agregación desconocida: {op['agg_op']}",
                )
            agg_req = aggregation_pb2.AggregateRequest(
                db_name    = op["db_name"],
                table_name = op["table_name"],
                operation  = agg_op,
                field      = op.get("agg_field", ""),
                filter     = _to_struct(op.get("filter", {})),
            )
            if op["agg_op"] == "INNER_JOIN" and op.get("join"):
                j = op["join"]
                agg_req.join.CopyFrom(aggregation_pb2.JoinConfig(
                    right_db    = j.get("right_db", op["db_name"]),
                    right_table = j["right_table"],
                    left_key    = j["left_key"],
                    right_key   = j["right_key"],
                ))
            resp = grpc_clients.aggregation_stub().Aggregate(agg_req)
            result_dict = {
                "success":       resp.success,
                "scalar_result": resp.scalar_result,
                "rows":          [dict(json_format.MessageToDict(r)) for r in resp.rows],
                "message":       resp.message,
            }

        # Empaquetar respuesta ──────────────────────────────────────
        if not result_dict.get("success"):
            return query_pb2.QueryResponse(
                success=False, message=result_dict.get("message", "Error en agregación")
            )

        if op["agg_op"] in ("DISTINCT", "INNER_JOIN"):
            structs = [_to_struct(r) for r in result_dict.get("rows", [])]
            return query_pb2.QueryResponse(
                success=True,
                rows=structs,
                affected_rows=len(structs),
                message=result_dict.get("message", ""),
            )
        else:
            scalar = result_dict.get("scalar_result", 0.0)
            return query_pb2.QueryResponse(
                success=True,
                rows=[_to_struct({"result": scalar})],
                affected_rows=1,
                message=result_dict.get("message", ""),
            )

    return query_pb2.QueryResponse(
        success=False,
        message=f"Operación '{kind}' no reconocida",
    )


# ── Servicer ───────────────────────────────────────────────────────

class QueryServicer(query_pb2_grpc.QueryServiceServicer):

    def ExecuteSQL(self, request, context) -> query_pb2.QueryResponse:
        sql = request.sql.strip()
        log.info(f"ExecuteSQL: {sql[:120]}")

        try:
            op = parse_sql(sql)
        except ValueError as exc:
            log.warning(f"Parse error: {exc}")
            return query_pb2.QueryResponse(success=False, message=str(exc))

        log.info(f"  → op={op['op']} db={op.get('db_name')} table={op.get('table_name')}")

        try:
            return _dispatch(op)
        except grpc.RpcError as exc:
            msg = f"Error en servicio interno: {exc.details()}"
            log.error(msg)
            return query_pb2.QueryResponse(success=False, message=msg)

    def ExecuteNoSQL(self, request, context) -> query_pb2.QueryResponse:
        operation = request.operation
        payload   = _from_struct(request.payload)
        log.info(f"ExecuteNoSQL: op={operation} db={request.db_name} col={request.collection}")

        # Traducir payload NoSQL → dict de operación normalizado
        op: dict = {
            "db_name":    request.db_name,
            "table_name": request.collection,
        }

        try:
            if operation == "insert":
                op["op"]     = "insert"
                op["record"] = payload.get("record", {})

            elif operation == "find":
                op["op"]     = "find"
                op["filter"] = payload.get("filter", {})
                op["limit"]  = int(payload.get("limit",  0))
                op["offset"] = int(payload.get("offset", 0))

            elif operation == "update":
                op["op"]      = "update"
                op["filter"]  = payload.get("filter",  {})
                op["updates"] = payload.get("updates", {})

            elif operation == "delete":
                op["op"]     = "delete"
                op["filter"] = payload.get("filter", {})

            elif operation == "aggregate":
                agg_op_str = str(payload.get("op", "COUNT")).upper()
                op["op"]        = "aggregate"
                op["agg_op"]    = agg_op_str
                op["agg_field"] = payload.get("field", "")
                op["filter"]    = payload.get("filter", {})
                if agg_op_str == "INNER_JOIN":
                    op["join"] = payload.get("join", {})

            else:
                return query_pb2.QueryResponse(
                    success=False,
                    message=f"Operación NoSQL no soportada: '{operation}'",
                )

            return _dispatch(op)

        except grpc.RpcError as exc:
            msg = f"Error en servicio interno: {exc.details()}"
            log.error(msg)
            return query_pb2.QueryResponse(success=False, message=msg)
        except Exception as exc:
            log.error(f"ExecuteNoSQL error: {exc}")
            return query_pb2.QueryResponse(success=False, message=str(exc))


# ── Server ─────────────────────────────────────────────────────────

def serve() -> None:
    grpc_clients.init_channels()

    port = os.getenv("GRPC_PORT", "50054")
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ("grpc.max_send_message_length",    32 * 1024 * 1024),
            ("grpc.max_receive_message_length", 32 * 1024 * 1024),
        ],
    )
    query_pb2_grpc.add_QueryServiceServicer_to_server(QueryServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info(f"✅ Query Service escuchando en puerto {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
