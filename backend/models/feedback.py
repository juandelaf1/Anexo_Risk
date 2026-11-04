"""Persistencia del bucle de feedback (predicciones y resultados observados).

La tabla `feedback_loop` se crea con la migración 016. Este módulo no
introduce un almacén paralelo: usa la misma SQLite y las mismas conexiones
que el resto del backend.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from db.database import get_connection

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feedback_loop (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    prediction_source TEXT NOT NULL,
    model_version TEXT,
    predicted_level TEXT,
    predicted_score REAL,
    prediction_time TEXT NOT NULL,
    h3_index TEXT,
    lat REAL,
    lon REAL,
    needs_open_at_prediction INTEGER,
    resources_available_at_prediction INTEGER,
    incident_id TEXT,
    outcome_time TEXT,
    incident_closed INTEGER DEFAULT 0,
    needs_created INTEGER DEFAULT 0,
    needs_resolved INTEGER DEFAULT 0,
    resource_gap_at_outcome INTEGER DEFAULT 0,
    response_duration_hours REAL,
    escalation_occurred INTEGER DEFAULT 0,
    metadata TEXT
)
"""


def init_feedback_table() -> None:
    """Garantiza que la tabla exista incluso en bases creadas antes de 016."""
    conn = get_connection()
    try:
        conn.execute(_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row) -> dict[str, Any]:
    result = dict(row)
    raw_metadata = result.get("metadata")
    if raw_metadata:
        try:
            result["metadata"] = json.loads(raw_metadata)
        except (TypeError, ValueError):
            pass
    return result


def record_prediction(
    prediction_source: str,
    model_version: Optional[str],
    predicted_level: str,
    predicted_score: float,
    prediction_time: Optional[str] = None,
    h3_index: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    needs_open: Optional[int] = None,
    resources_available: Optional[int] = None,
    incident_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict[str, Any]:
    """Registra una predicción para poder compararla después con el resultado."""
    init_feedback_table()
    prediction_time = prediction_time or datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO feedback_loop (
                prediction_source, model_version, predicted_level,
                predicted_score, prediction_time, h3_index, lat, lon,
                needs_open_at_prediction, resources_available_at_prediction,
                incident_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction_source,
                model_version,
                predicted_level,
                predicted_score,
                prediction_time,
                h3_index,
                lat,
                lon,
                needs_open,
                resources_available,
                incident_id,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        feedback_id = cur.lastrowid
    finally:
        conn.close()
    return {
        "status": "recorded",
        "id": feedback_id,
        "prediction_time": prediction_time,
    }


def record_outcome(
    feedback_id: int,
    incident_closed: bool = False,
    needs_created: int = 0,
    needs_resolved: int = 0,
    resource_gap: int = 0,
    response_duration_hours: Optional[float] = None,
    escalation_occurred: bool = False,
    metadata: Optional[dict] = None,
) -> Optional[dict[str, Any]]:
    """Completa el resultado observado de una predicción existente."""
    init_feedback_table()
    outcome_time = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT metadata FROM feedback_loop WHERE id = ?", (feedback_id,)
        ).fetchone()
        if existing is None:
            return None
        merged_metadata = {}
        if existing["metadata"]:
            try:
                merged_metadata = json.loads(existing["metadata"])
            except (TypeError, ValueError):
                merged_metadata = {}
        merged_metadata.update(metadata or {})
        conn.execute(
            """
            UPDATE feedback_loop SET
                outcome_time = ?,
                incident_closed = ?,
                needs_created = ?,
                needs_resolved = ?,
                resource_gap_at_outcome = ?,
                response_duration_hours = ?,
                escalation_occurred = ?,
                metadata = ?
            WHERE id = ?
            """,
            (
                outcome_time,
                1 if incident_closed else 0,
                needs_created,
                needs_resolved,
                resource_gap,
                response_duration_hours,
                1 if escalation_occurred else 0,
                json.dumps(merged_metadata, ensure_ascii=False),
                feedback_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "outcome_recorded", "id": feedback_id, "outcome_time": outcome_time}


def get_feedback_entries(
    h3_index: Optional[str] = None,
    prediction_source: Optional[str] = None,
    has_outcome: Optional[bool] = None,
    incident_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Devuelve entradas de feedback con filtros opcionales."""
    init_feedback_table()
    clauses = []
    params: list[Any] = []
    if h3_index:
        clauses.append("h3_index = ?")
        params.append(h3_index)
    if prediction_source:
        clauses.append("prediction_source = ?")
        params.append(prediction_source)
    if incident_id:
        clauses.append("incident_id = ?")
        params.append(incident_id)
    if has_outcome is True:
        clauses.append("outcome_time IS NOT NULL")
    elif has_outcome is False:
        clauses.append("outcome_time IS NULL")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([max(1, min(limit, 1000)), max(0, offset)])
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT * FROM feedback_loop {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            tuple(params),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(row) for row in rows]


def get_feedback_stats() -> dict[str, Any]:
    """Estadísticas agregadas del bucle de feedback."""
    init_feedback_table()
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM feedback_loop").fetchone()["n"]
        with_outcome = conn.execute(
            "SELECT COUNT(*) AS n FROM feedback_loop WHERE outcome_time IS NOT NULL"
        ).fetchone()["n"]
        closed = conn.execute(
            "SELECT COUNT(*) AS n FROM feedback_loop WHERE incident_closed = 1"
        ).fetchone()["n"]
        escalated = conn.execute(
            "SELECT COUNT(*) AS n FROM feedback_loop WHERE escalation_occurred = 1"
        ).fetchone()["n"]
    finally:
        conn.close()
    return {
        "total_predictions": total,
        "with_outcome": with_outcome,
        "without_outcome": total - with_outcome,
        "incidents_closed": closed,
        "escalations": escalated,
    }
