"""
sql_parser.py — convierte un string SQL a un dict de operación normalizado.
"""
from __future__ import annotations
import sqlglot
import sqlglot.expressions as exp


def parse_sql(sql: str) -> dict:
    try:
        tree = sqlglot.parse_one(sql.strip())
    except Exception as exc:
        raise ValueError(f"SQL inválido: {exc}")

    if isinstance(tree, exp.Select):
        return _parse_select(tree)
    if isinstance(tree, exp.Insert):
        return _parse_insert(tree)
    if isinstance(tree, exp.Update):
        return _parse_update(tree)
    if isinstance(tree, exp.Delete):
        return _parse_delete(tree)

    raise ValueError(f"Operación no soportada: {type(tree).__name__}. Usa SELECT, INSERT, UPDATE o DELETE.")


# ── SELECT ─────────────────────────────────────────────────────────

def _parse_select(tree: exp.Select) -> dict:
    table, db_name, table_name = _extract_table(tree)

    join_node = tree.find(exp.Join)
    if join_node:
        return _parse_join(tree, db_name, table_name, join_node)

    count_node = tree.find(exp.Count)
    if count_node:
        return {"op":"aggregate","db_name":db_name,"table_name":table_name,
                "agg_op":"COUNT","agg_field":"",
                "filter":_parse_where(tree.find(exp.Where)),"limit":0,"offset":0}

    for agg_cls, agg_name in ((exp.Sum,"SUM"),(exp.Avg,"AVG")):
        agg_node = tree.find(agg_cls)
        if agg_node:
            field = _col_name(agg_node.this)
            return {"op":"aggregate","db_name":db_name,"table_name":table_name,
                    "agg_op":agg_name,"agg_field":field,
                    "filter":_parse_where(tree.find(exp.Where)),"limit":0,"offset":0}

    if tree.args.get("distinct"):
        col_expr = tree.expressions[0]
        field = col_expr.name if hasattr(col_expr,"name") else col_expr.sql()
        return {"op":"aggregate","db_name":db_name,"table_name":table_name,
                "agg_op":"DISTINCT","agg_field":field,
                "filter":_parse_where(tree.find(exp.Where)),"limit":0,"offset":0}

    columns = []
    for col_expr in tree.expressions:
        if isinstance(col_expr, exp.Star):
            columns = []
            break
        columns.append(_col_name(col_expr))

    limit_node  = tree.find(exp.Limit)
    offset_node = tree.find(exp.Offset)

    return {"op":"find","db_name":db_name,"table_name":table_name,
            "filter":_parse_where(tree.find(exp.Where)),"columns":columns,
            "limit":int(limit_node.this.this) if limit_node else 0,
            "offset":int(offset_node.this.this) if offset_node else 0}


def _parse_join(tree, db_name, table_name, join_node) -> dict:
    right_table = join_node.this
    right_db    = right_table.db or db_name
    right_name  = right_table.name

    on_node = join_node.args.get("on")
    if on_node is None:
        raise ValueError("INNER JOIN requiere cláusula ON")

    cond = on_node if isinstance(on_node, exp.EQ) else on_node.find(exp.EQ)
    if cond is None:
        raise ValueError("La condición ON debe ser una igualdad (t1.col = t2.col)")

    left_key  = _col_name(cond.this)
    right_key = _col_name(cond.expression)

    return {"op":"aggregate","db_name":db_name,"table_name":table_name,
            "agg_op":"INNER_JOIN","agg_field":"",
            "filter":_parse_where(tree.find(exp.Where)),
            "join":{"right_db":right_db,"right_table":right_name,
                    "left_key":left_key,"right_key":right_key},
            "limit":0,"offset":0}


# ── INSERT ─────────────────────────────────────────────────────────

def _parse_insert(tree: exp.Insert) -> dict:
    # sqlglot >= 20: INSERT INTO t (col1, col2) VALUES (...)
    # genera Schema(this=Table, expressions=[col1, col2])
    schema_or_table = tree.this
    if isinstance(schema_or_table, exp.Schema):
        table_node = schema_or_table.this
        col_names  = [c.name for c in schema_or_table.expressions]
    else:
        table_node = schema_or_table or tree.find(exp.Table)
        col_names  = [c.name for c in (tree.args.get("columns") or [])]

    db_name, table_name = _db_table(table_node)

    values_node = tree.find(exp.Values)
    if not values_node:
        raise ValueError("INSERT sin VALUES")

    tuple_node = values_node.find(exp.Tuple)
    if not tuple_node:
        raise ValueError("No se encontraron valores en INSERT")

    raw_vals = [_literal_value(v) for v in tuple_node.expressions]

    if col_names and len(col_names) != len(raw_vals):
        raise ValueError(f"Columnas ({len(col_names)}) no coinciden con valores ({len(raw_vals)})")

    record = (dict(zip(col_names, raw_vals)) if col_names
              else {f"col{i}": v for i, v in enumerate(raw_vals)})

    return {"op":"insert","db_name":db_name,"table_name":table_name,"record":record}


# ── UPDATE ─────────────────────────────────────────────────────────

def _parse_update(tree: exp.Update) -> dict:
    table_node = tree.find(exp.Table)
    db_name, table_name = _db_table(table_node)

    where_node = tree.find(exp.Where)
    where_eqs  = set(id(e) for e in (where_node.find_all(exp.EQ) if where_node else []))

    updates = {}
    for eq in tree.find_all(exp.EQ):
        if id(eq) in where_eqs:
            continue
        col = _col_name(eq.this)
        val = _literal_value(eq.expression)
        updates[col] = val

    return {"op":"update","db_name":db_name,"table_name":table_name,
            "updates":updates,"filter":_parse_where(where_node)}


# ── DELETE ─────────────────────────────────────────────────────────

def _parse_delete(tree: exp.Delete) -> dict:
    table_node = tree.find(exp.Table)
    db_name, table_name = _db_table(table_node)
    return {"op":"delete","db_name":db_name,"table_name":table_name,
            "filter":_parse_where(tree.find(exp.Where))}


# ── WHERE → filter dict ────────────────────────────────────────────

def _parse_where(where_node) -> dict:
    if where_node is None:
        return {}
    return _parse_condition(where_node.this)


def _parse_condition(node) -> dict:
    if node is None:
        return {}
    if isinstance(node, exp.And):
        result = {}
        result.update(_parse_condition(node.left))
        result.update(_parse_condition(node.right))
        return result
    _CMP = {exp.EQ:None,exp.GT:"$gt",exp.GTE:"$gte",
            exp.LT:"$lt",exp.LTE:"$lte",exp.NEQ:"$ne",exp.Like:"$like"}
    for cls, op in _CMP.items():
        if isinstance(node, cls):
            col = _col_name(node.this)
            val = _literal_value(node.expression)
            return {col: val} if op is None else {col: {op: val}}
    raise ValueError(f"Condición WHERE no soportada: '{node.sql()}'. Usa =, !=, >, >=, <, <=, LIKE o AND.")


# ── Helpers ────────────────────────────────────────────────────────

def _extract_table(tree) -> tuple:
    from_node = tree.find(exp.From)
    if from_node:
        table_node = from_node.find(exp.Table)
    else:
        table_node = tree.find(exp.Table)
    if not table_node:
        raise ValueError("No se encontró la tabla en la consulta")
    db_name, table_name = _db_table(table_node)
    return table_node, db_name, table_name


def _db_table(table_node) -> tuple:
    if table_node is None:
        raise ValueError("No se encontró la tabla en la consulta")
    db    = table_node.db   or ""
    table = table_node.name or ""
    if not table:
        raise ValueError("Nombre de tabla vacío")
    if not db:
        raise ValueError(f"Debes especificar la base de datos: usa 'db_name.{table}' en el SQL")
    return db, table


def _col_name(node) -> str:
    if isinstance(node, exp.Column):
        return node.name
    if isinstance(node, exp.Identifier):
        return node.name
    if hasattr(node, "name"):
        return node.name
    return node.sql().strip('"').strip("'")


def _literal_value(node):
    if isinstance(node, exp.Literal):
        if node.is_string:
            return node.this
        raw = node.this
        try:
            return int(raw)
        except ValueError:
            return float(raw)
    if isinstance(node, exp.Boolean):
        return bool(node.this)
    if isinstance(node, exp.Null):
        return None
    return node.sql().strip("'\"")
