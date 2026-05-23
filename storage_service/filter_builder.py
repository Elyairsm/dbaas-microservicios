"""
filter_builder.py — traduce un dict de filtros a cláusula SQL WHERE.

Dos sintaxis soportadas:

  1. Igualdad simple (la más común):
       {"nombre": "Ana", "edad": 25}
       → WHERE "nombre" = ? AND "edad" = ?

  2. Operadores explícitos (estilo MongoDB-like):
       {"edad": {"$gt": 18}, "precio": {"$lte": 500.0}}
       → WHERE "edad" > ? AND "precio" <= ?

Operadores disponibles:
  $eq   →  =       (igual)
  $ne   →  !=      (distinto)
  $gt   →  >       (mayor que)
  $gte  →  >=      (mayor o igual)
  $lt   →  <       (menor que)
  $lte  →  <=      (menor o igual)
  $like →  LIKE    (patrón, usa % como comodín: "Ana%")
  $in   →  IN (...)

Si el dict de filtros está vacío → sin cláusula WHERE (match all).
"""
from __future__ import annotations

_OP_MAP: dict[str, str] = {
    "$eq":   "=",
    "$ne":   "!=",
    "$gt":   ">",
    "$gte":  ">=",
    "$lt":   "<",
    "$lte":  "<=",
    "$like": "LIKE",
}


def build_where(filter_dict: dict) -> tuple[str, list]:
    """
    Retorna (where_clause, params).
    where_clause: string listo para agregar después de WHERE (o vacío).
    params: lista de valores para la query parametrizada.
    """
    if not filter_dict:
        return "", []

    clauses: list[str] = []
    params:  list      = []

    for field, value in filter_dict.items():
        safe_field = f'"{field}"'

        if isinstance(value, dict):
            # Operadores: {"$gt": 18} o varios: {"$gte": 10, "$lte": 20}
            for op_key, op_val in value.items():
                if op_key == "$in":
                    if not isinstance(op_val, list):
                        raise ValueError(f"$in requiere una lista, recibió {type(op_val)}")
                    placeholders = ", ".join("?" * len(op_val))
                    clauses.append(f"{safe_field} IN ({placeholders})")
                    params.extend(op_val)
                else:
                    sql_op = _OP_MAP.get(op_key)
                    if not sql_op:
                        raise ValueError(
                            f"Operador desconocido: '{op_key}'. "
                            f"Usa uno de: {list(_OP_MAP.keys()) + ['$in']}"
                        )
                    clauses.append(f"{safe_field} {sql_op} ?")
                    params.append(op_val)
        else:
            # Igualdad directa
            clauses.append(f"{safe_field} = ?")
            params.append(value)

    return " AND ".join(clauses), params
