"""
rabbitmq_consumer.py — consumer del Aggregation Service.

Escucha en 'aggregation_queue', procesa cada petición con MPI
y publica el resultado en la reply queue del Query Service.

Corre en un hilo background separado del servidor gRPC para que
ambos puedan operar concurrentemente.

Formato de mensajes: ver query_service/rabbitmq_rpc.py
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

import pika

import aggregator
import storage_client

log = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://dbaas:dbaas123@rabbitmq:5672/")
AGG_QUEUE    = "aggregation_queue"
RETRY_DELAY  = 5   # segundos entre reintentos de conexión


# ── Lógica de agregación compartida ───────────────────────────────

def _process(request: dict) -> dict:
    """
    Ejecuta la agregación solicitada y retorna un dict de respuesta.
    Comparte exactamente la misma lógica que el servicer gRPC
    para no duplicar código.
    """
    db_name    = request.get("db_name", "")
    table_name = request.get("table_name", "")
    operation  = str(request.get("operation", "")).upper()
    field      = request.get("field", "")
    filter_d   = request.get("filter") or {}

    log.info(f"[RabbitMQ] Aggregate op={operation} {db_name}.{table_name}")

    # Obtener registros
    ok, msg, records = storage_client.fetch_records(db_name, table_name, filter_d)
    if not ok:
        return {"success": False, "scalar_result": 0.0, "rows": [], "message": msg}

    log.info(f"[RabbitMQ]   Records: {len(records)}")

    try:
        if operation == "COUNT":
            result = aggregator.count(records)
            return {"success": True, "scalar_result": result, "rows": [],
                    "message": f"COUNT = {int(result)}"}

        if operation == "SUM":
            if not field:
                return {"success": False, "scalar_result": 0.0, "rows": [],
                        "message": "SUM requiere un campo"}
            result = aggregator.aggregate_sum(records, field)
            return {"success": True, "scalar_result": result, "rows": [],
                    "message": f"SUM({field}) = {result}"}

        if operation == "AVG":
            if not field:
                return {"success": False, "scalar_result": 0.0, "rows": [],
                        "message": "AVG requiere un campo"}
            result = aggregator.avg(records, field)
            return {"success": True, "scalar_result": result, "rows": [],
                    "message": f"AVG({field}) = {result:.4f}"}

        if operation == "DISTINCT":
            if not field:
                return {"success": False, "scalar_result": 0.0, "rows": [],
                        "message": "DISTINCT requiere un campo"}
            rows = aggregator.distinct(records, field)
            return {"success": True, "scalar_result": 0.0, "rows": rows,
                    "message": f"DISTINCT {field} → {len(rows)} valores"}

        if operation == "INNER_JOIN":
            join_cfg = request.get("join") or {}
            if not join_cfg.get("right_table"):
                return {"success": False, "scalar_result": 0.0, "rows": [],
                        "message": "INNER_JOIN requiere join.right_table"}

            right_db    = join_cfg.get("right_db") or db_name
            right_table = join_cfg["right_table"]
            left_key    = join_cfg.get("left_key", "")
            right_key   = join_cfg.get("right_key", "")

            ok2, msg2, right_records = storage_client.fetch_records(
                right_db, right_table, {}
            )
            if not ok2:
                return {"success": False, "scalar_result": 0.0, "rows": [],
                        "message": msg2}

            joined = aggregator.inner_join(records, right_records, left_key, right_key)
            return {"success": True, "scalar_result": 0.0, "rows": joined,
                    "message": f"INNER JOIN → {len(joined)} registros"}

        return {"success": False, "scalar_result": 0.0, "rows": [],
                "message": f"Operación no reconocida: {operation}"}

    except Exception as exc:
        log.error(f"[RabbitMQ] Error en agregación: {exc}", exc_info=True)
        return {"success": False, "scalar_result": 0.0, "rows": [], "message": str(exc)}


# ── Consumer ───────────────────────────────────────────────────────

def _run_consumer() -> None:
    """Loop principal del consumer con reconexión automática."""
    while True:
        try:
            connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            channel    = connection.channel()

            channel.queue_declare(queue=AGG_QUEUE, durable=True)
            channel.basic_qos(prefetch_count=1)   # un mensaje a la vez por worker

            def _on_request(ch, method, props, body):
                try:
                    request  = json.loads(body.decode("utf-8"))
                    response = _process(request)
                except Exception as exc:
                    log.error(f"[RabbitMQ] Error deserializando mensaje: {exc}")
                    response = {"success": False, "scalar_result": 0.0,
                                "rows": [], "message": str(exc)}

                # Publicar respuesta en la reply queue del Query Service
                if props.reply_to:
                    ch.basic_publish(
                        exchange="",
                        routing_key=props.reply_to,
                        properties=pika.BasicProperties(
                            correlation_id=props.correlation_id,
                            content_type="application/json",
                        ),
                        body=json.dumps(response).encode("utf-8"),
                    )

                ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=AGG_QUEUE, on_message_callback=_on_request)
            log.info(f"✅ RabbitMQ consumer escuchando en '{AGG_QUEUE}'")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as exc:
            log.warning(f"[RabbitMQ] Conexión perdida: {exc}. Reintentando en {RETRY_DELAY}s…")
            time.sleep(RETRY_DELAY)
        except Exception as exc:
            log.error(f"[RabbitMQ] Error inesperado: {exc}. Reintentando en {RETRY_DELAY}s…")
            time.sleep(RETRY_DELAY)


def start_in_background() -> threading.Thread:
    """Arranca el consumer en un hilo daemon."""
    t = threading.Thread(target=_run_consumer, name="rabbitmq-consumer", daemon=True)
    t.start()
    log.info("Thread RabbitMQ consumer iniciado")
    return t
