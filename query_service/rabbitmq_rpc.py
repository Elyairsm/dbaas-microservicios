"""
rabbitmq_rpc.py — cliente RPC sobre RabbitMQ para el Query Service.

Patrón usado: RabbitMQ RPC (Direct Reply-To).
  1. Query Service crea una cola exclusiva de respuesta.
  2. Publica el request en 'aggregation_queue' con:
       reply_to      = nombre de la cola de respuesta
       correlation_id = UUID único de la petición
  3. Espera en su cola de respuesta hasta recibir el mensaje
     con el mismo correlation_id.
  4. Deserializa y retorna el resultado.

Cada llamada crea su propia conexión pika → thread-safe sin locks.

Formato del mensaje (JSON):
  Request:  {"db_name":..., "table_name":..., "operation":...,
             "field":..., "filter":{...}, "join":{...}|null}
  Response: {"success":true|false, "scalar_result":0.0,
             "rows":[...], "message":"..."}
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid

import pika

log = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://dbaas:dbaas123@rabbitmq:5672/")
AGG_QUEUE    = "aggregation_queue"
TIMEOUT      = int(os.getenv("AGG_TIMEOUT_SECONDS", "60"))


def call(request: dict) -> dict:
    """
    Envía una petición de agregación via RabbitMQ y espera la respuesta.
    Retorna el dict de respuesta del Aggregation Service.
    Lanza TimeoutError si no hay respuesta en TIMEOUT segundos.
    Lanza ConnectionError si RabbitMQ no está disponible.
    """
    try:
        params     = pika.URLParameters(RABBITMQ_URL)
        connection = pika.BlockingConnection(params)
    except Exception as exc:
        raise ConnectionError(f"No se pudo conectar a RabbitMQ: {exc}") from exc

    channel = connection.channel()

    # Cola exclusiva para esta respuesta (se elimina al cerrar la conexión)
    result      = channel.queue_declare(queue="", exclusive=True)
    reply_queue = result.method.queue
    corr_id     = str(uuid.uuid4())

    response: list[dict | None] = [None]

    def _on_response(ch, method, props, body):
        if props.correlation_id == corr_id:
            response[0] = json.loads(body.decode("utf-8"))

    channel.basic_consume(
        queue=reply_queue,
        on_message_callback=_on_response,
        auto_ack=True,
    )

    # Publicar la petición
    channel.basic_publish(
        exchange="",
        routing_key=AGG_QUEUE,
        properties=pika.BasicProperties(
            reply_to=reply_queue,
            correlation_id=corr_id,
            content_type="application/json",
            delivery_mode=1,   # no persistente → más rápido
        ),
        body=json.dumps(request).encode("utf-8"),
    )

    log.debug(f"RabbitMQ: publicado corr_id={corr_id[:8]}… op={request.get('operation')}")

    # Esperar respuesta con timeout
    deadline = time.monotonic() + TIMEOUT
    while response[0] is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            connection.close()
            raise TimeoutError(
                f"Aggregation Service no respondió en {TIMEOUT}s "
                f"(op={request.get('operation')})"
            )
        connection.process_data_events(time_limit=min(1.0, remaining))

    connection.close()
    log.debug(f"RabbitMQ: respuesta recibida corr_id={corr_id[:8]}…")
    return response[0]
