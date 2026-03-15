"""
Review Cycle Engine
Handles: POST /cycles, GET /cycles, GET /cycles/{cycle_id}
On creation: validates input, writes to DynamoDB, starts Step Functions execution
"""

import json
import os
import uuid
import boto3
from datetime import datetime, timezone, timedelta
from typing import Any
from decimal_encoder import DecimalEncoder

dynamodb = boto3.resource("dynamodb")
sfn = boto3.client("stepfunctions")

CYCLES_TABLE = os.environ["CYCLES_TABLE"]
EMPLOYEES_TABLE = os.environ["EMPLOYEES_TABLE"]
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]


def lambda_handler(event: dict, context: Any) -> dict:
    method = event["httpMethod"]
    path = event["resource"]

    try:
        if method == "POST" and path == "/cycles":
            return create_cycle(event)
        elif method == "GET" and path == "/cycles":
            return list_cycles(event)
        elif method == "GET" and path == "/cycles/{cycle_id}":
            return get_cycle(event)
        elif method == "DELETE" and path == "/cycles/{cycle_id}":
            return delete_cycle(event)
        elif method == "GET" and path == "/employees":
            return list_employees(event)
        else:
            return response(404, {"error": "Route not found"})
    except ValueError as e:
        return response(400, {"error": str(e)})
    except Exception as e:
        print(f"ERROR: {e}")
        return response(500, {"error": "Internal server error"})


# ─── Create Cycle ─────────────────────────────────────────────────────────────

def create_cycle(event: dict) -> dict:
    body = json.loads(event.get("body") or "{}")
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_role = claims.get("custom:role", "")

    if caller_role != "hr_admin":
        return response(403, {"error": "Only HR Admin can create review cycles"})

    # Validate required fields
    required = ["name", "start_date", "end_date", "employee_ids"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    start_date = body["start_date"]  # ISO: 2025-10-01
    end_date = body["end_date"]
    employee_ids = body["employee_ids"]

    if not isinstance(employee_ids, list) or len(employee_ids) == 0:
        raise ValueError("employee_ids must be a non-empty list")

    # Validate employees exist
    table_employees = dynamodb.Table(EMPLOYEES_TABLE)
    for emp_id in employee_ids:
        result = table_employees.get_item(Key={"employee_id": emp_id})
        if "Item" not in result:
            raise ValueError(f"Employee not found: {emp_id}")

    cycle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Build reminder timestamps for Step Functions
    # 3-day and 1-day reminders before end_date
    end_dt = datetime.fromisoformat(end_date + "T23:59:00+00:00")
    reminder_3day = (end_dt - timedelta(days=3)).isoformat()
    reminder_1day = (end_dt - timedelta(days=1)).isoformat()

    cycle_item = {
        "cycle_id": cycle_id,
        "name": body["name"],
        "start_date": start_date,
        "end_date": end_date,
        "employee_ids": employee_ids,
        "status": "active",
        "created_by": claims.get("sub"),
        "created_at": now,
        "submission_stats": {
            "total_employees": len(employee_ids),
            "self_reviews_submitted": 0,
            "manager_reviews_submitted": 0,
            "peer_reviews_submitted": 0,
        },
    }

    dynamodb.Table(CYCLES_TABLE).put_item(Item=cycle_item)

    # Start Step Functions workflow
    sfn_input = {
        "cycle_id": cycle_id,
        "reminder_3day_at": reminder_3day,
        "reminder_1day_at": reminder_1day,
        "deadline_at": end_dt.isoformat(),
    }

    sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=f"cycle-{cycle_id}",
        input=json.dumps(sfn_input),
    )

    return response(201, {
        "message": "Review cycle created",
        "cycle_id": cycle_id,
        "cycle": cycle_item,
    })


# ─── List Cycles ──────────────────────────────────────────────────────────────

def list_cycles(event: dict) -> dict:
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_role = claims.get("custom:role", "")
    caller_employee_id = claims.get("custom:employee_id", "")

    table = dynamodb.Table(CYCLES_TABLE)

    if caller_role in ("hr_admin", "manager"):
        # HR and managers see all cycles
        result = table.scan()
        cycles = result.get("Items", [])
    else:
        # Employees see only cycles they are part of
        result = table.scan(
            FilterExpression="contains(employee_ids, :eid)",
            ExpressionAttributeValues={":eid": caller_employee_id},
        )
        cycles = result.get("Items", [])

    # Sort by start_date descending
    cycles.sort(key=lambda c: c.get("start_date", ""), reverse=True)

    return response(200, {"cycles": cycles, "count": len(cycles)})


# ─── Get Single Cycle ─────────────────────────────────────────────────────────

def get_cycle(event: dict) -> dict:
    cycle_id = event["pathParameters"]["cycle_id"]
    result = dynamodb.Table(CYCLES_TABLE).get_item(Key={"cycle_id": cycle_id})

    if "Item" not in result:
        return response(404, {"error": "Cycle not found"})

    return response(200, {"cycle": result["Item"]})


# ─── List Employees ───────────────────────────────────────────────────────────

def list_employees(event: dict) -> dict:
    """Return all employees for the cycle creation form."""
    result = dynamodb.Table(EMPLOYEES_TABLE).scan()
    employees = [
        {
            "employee_id": e["employee_id"],
            "name": e.get("name", e["employee_id"]),
            "role": e.get("role", ""),
            "department": e.get("department", ""),
            "cognito_role": e.get("cognito_role", "employee"),
        }
        for e in result.get("Items", [])
        if e.get("cognito_role") == "employee"  # only show employees, not managers/HR
    ]
    employees.sort(key=lambda e: e["name"])
    return response(200, {"employees": employees})


# ─── Delete Cycle ─────────────────────────────────────────────────────────────

def delete_cycle(event: dict) -> dict:
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_role = claims.get("custom:role", "")
    if caller_role != "hr_admin":
        return response(403, {"error": "Only HR Admin can delete review cycles"})

    cycle_id = event["pathParameters"]["cycle_id"]
    result = dynamodb.Table(CYCLES_TABLE).get_item(Key={"cycle_id": cycle_id})
    if "Item" not in result:
        return response(404, {"error": "Cycle not found"})

    dynamodb.Table(CYCLES_TABLE).delete_item(Key={"cycle_id": cycle_id})
    return response(200, {"message": "Cycle deleted", "cycle_id": cycle_id})


# ─── Helper ───────────────────────────────────────────────────────────────────

def response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, cls=DecimalEncoder),
    }
