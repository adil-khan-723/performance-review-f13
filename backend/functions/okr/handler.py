"""
OKR Tracking Lambda
Handles:
  POST /okr               — create objective with key results
  PUT  /okr/{okr_id}     — update KR progress (0-100%)
  GET  /okr/{employee_id} — get all OKRs for an employee

Weekly EventBridge trigger — sends progress update prompts via SES
"""

import json
import os
import uuid
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr
from decimal_encoder import DecimalEncoder

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("ses")

OKR_TABLE = os.environ["OKR_TABLE"]
EMPLOYEES_TABLE = os.environ["EMPLOYEES_TABLE"]
SES_SENDER = os.environ["SES_SENDER_EMAIL"]


def lambda_handler(event: dict, context) -> dict:
    # Weekly EventBridge trigger has no httpMethod
    if "httpMethod" not in event:
        return send_weekly_prompts(event)

    method = event["httpMethod"]
    path = event["resource"]

    try:
        if method == "POST" and path == "/okr":
            return create_okr(event)
        elif method == "PUT" and path == "/okr/{okr_id}":
            return update_okr(event)
        elif method == "GET" and path == "/okr/employee/{employee_id}":
            return get_okrs(event)
        else:
            return response(404, {"error": "Route not found"})
    except ValueError as e:
        return response(400, {"error": str(e)})
    except Exception as e:
        print(f"ERROR: {e}")
        return response(500, {"error": "Internal server error"})


# ─── Create OKR ───────────────────────────────────────────────────────────────

def create_okr(event: dict) -> dict:
    body = json.loads(event.get("body") or "{}")
    claims = event["requestContext"]["authorizer"]["claims"]
    employee_id = claims.get("custom:employee_id")

    required = ["objective_title", "quarter", "key_results"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    key_results = body["key_results"]
    if not isinstance(key_results, list) or len(key_results) == 0:
        raise ValueError("key_results must be a non-empty list")
    if len(key_results) > 3:
        raise ValueError("Maximum 3 key results per objective")

    # Validate each KR
    validated_krs = []
    for i, kr in enumerate(key_results):
        if not kr.get("title"):
            raise ValueError(f"Key result {i+1} missing title")
        if not kr.get("target_metric"):
            raise ValueError(f"Key result {i+1} missing target_metric")

        validated_krs.append({
            "kr_id": str(uuid.uuid4())[:8],
            "title": kr["title"],
            "target_metric": kr["target_metric"],
            "progress": 0,  # 0-100%
            "progress_history": [],
            "notes": kr.get("notes", ""),
        })

    # Validate quarter format e.g. "2025-Q4"
    quarter = body["quarter"]
    if not (len(quarter) == 7 and quarter[4] == "-" and quarter[5] == "Q"):
        raise ValueError("quarter must be in format YYYY-QN e.g. 2025-Q4")

    okr_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "okr_id": okr_id,
        "employee_id": employee_id,
        "objective_title": body["objective_title"],
        "quarter": quarter,
        "key_results": validated_krs,
        "overall_completion": 0,
        "created_at": now,
        "updated_at": now,
    }

    dynamodb.Table(OKR_TABLE).put_item(Item=item)

    return response(201, {"message": "OKR created", "okr_id": okr_id, "okr": item})


# ─── Update OKR Progress ──────────────────────────────────────────────────────

def update_okr(event: dict) -> dict:
    okr_id = event["pathParameters"]["okr_id"]
    body = json.loads(event.get("body") or "{}")
    claims = event["requestContext"]["authorizer"]["claims"]
    employee_id = claims.get("custom:employee_id")

    table = dynamodb.Table(OKR_TABLE)
    result = table.get_item(Key={"okr_id": okr_id})
    if "Item" not in result:
        return response(404, {"error": "OKR not found"})

    okr = result["Item"]
    if okr["employee_id"] != employee_id:
        return response(403, {"error": "You can only update your own OKRs"})

    # Expect: {"kr_updates": [{"kr_id": "...", "progress": 75, "notes": "..."}]}
    kr_updates = body.get("kr_updates", [])
    if not kr_updates:
        raise ValueError("kr_updates required")

    now = datetime.now(timezone.utc).isoformat()
    kr_map = {kr["kr_id"]: kr for kr in okr["key_results"]}

    for update in kr_updates:
        kr_id = update.get("kr_id")
        if kr_id not in kr_map:
            raise ValueError(f"Key result not found: {kr_id}")

        progress = update.get("progress")
        if progress is None or not isinstance(progress, (int, float)):
            raise ValueError(f"Progress must be a number for KR {kr_id}")
        if not (0 <= progress <= 100):
            raise ValueError(f"Progress must be 0-100 for KR {kr_id}")

        kr = kr_map[kr_id]
        kr["progress"] = progress
        kr["progress_history"].append({
            "progress": progress,
            "notes": update.get("notes", ""),
            "recorded_at": now,
        })
        if update.get("notes"):
            kr["notes"] = update["notes"]

    from decimal import Decimal
    updated_krs = list(kr_map.values())
    overall = Decimal(str(round(sum(float(kr["progress"]) for kr in updated_krs) / len(updated_krs), 1)))

    table.update_item(
        Key={"okr_id": okr_id},
        UpdateExpression="SET key_results = :krs, overall_completion = :oc, updated_at = :t",
        ExpressionAttributeValues={
            ":krs": updated_krs,
            ":oc": overall,
            ":t": now,
        },
    )

    return response(200, {
        "message": "OKR progress updated",
        "okr_id": okr_id,
        "overall_completion": overall,
        "key_results": updated_krs,
    })


# ─── Get OKRs ─────────────────────────────────────────────────────────────────

def get_okrs(event: dict) -> dict:
    # Route is /okr/employee/{employee_id}
    employee_id = event["pathParameters"]["employee_id"]
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_id = claims.get("custom:employee_id")
    caller_role = claims.get("custom:role", "")

    # Employees only view own; managers/HR can view anyone
    if caller_role == "employee" and caller_id != employee_id:
        return response(403, {"error": "Access denied"})

    params = event.get("queryStringParameters") or {}
    quarter = params.get("quarter")  # optional filter e.g. ?quarter=2025-Q4

    table = dynamodb.Table(OKR_TABLE)
    if quarter:
        result = table.query(
            IndexName="employee-quarter-index",
            KeyConditionExpression=Key("employee_id").eq(employee_id) & Key("quarter").eq(quarter),
        )
    else:
        result = table.query(
            IndexName="employee-quarter-index",
            KeyConditionExpression=Key("employee_id").eq(employee_id),
        )

    okrs = result.get("Items", [])
    okrs.sort(key=lambda o: o.get("quarter", ""), reverse=True)

    return response(200, {"employee_id": employee_id, "okrs": okrs, "count": len(okrs)})


# ─── Weekly EventBridge Prompt ────────────────────────────────────────────────

def send_weekly_prompts(event: dict) -> dict:
    """
    Triggered every Monday at 9am UTC via EventBridge cron.
    Emails all employees with active OKRs to update their progress.
    """
    current_quarter = get_current_quarter()

    # Scan all OKRs for current quarter with incomplete progress
    table = dynamodb.Table(OKR_TABLE)
    result = table.scan(
        FilterExpression=Attr("quarter").eq(current_quarter) & Attr("overall_completion").lt(100),
    )
    okrs = result.get("Items", [])

    # Group by employee
    by_employee: dict = {}
    for okr in okrs:
        eid = okr["employee_id"]
        by_employee.setdefault(eid, []).append(okr)

    notified = 0
    emp_table = dynamodb.Table(EMPLOYEES_TABLE)

    for employee_id, employee_okrs in by_employee.items():
        emp = emp_table.get_item(Key={"employee_id": employee_id}).get("Item")
        if not emp or not emp.get("email"):
            continue

        okr_summary = "".join(
            f"<li><strong>{o['objective_title']}</strong> — {o['overall_completion']}% complete</li>"
            for o in employee_okrs
        )

        body = f"""
        <h2>Weekly OKR Update Reminder</h2>
        <p>Hi {emp.get('name', 'there')},</p>
        <p>Please take a moment to update your OKR progress for <strong>{current_quarter}</strong>:</p>
        <ul>{okr_summary}</ul>
        <p>Log in to update your key results with the latest progress.</p>
        """

        try:
            ses.send_email(
                Source=SES_SENDER,
                Destination={"ToAddresses": [emp["email"]]},
                Message={
                    "Subject": {"Data": f"[OKR Update] Weekly progress reminder — {current_quarter}"},
                    "Body": {"Html": {"Data": body}},
                },
            )
            notified += 1
        except Exception as e:
            print(f"Failed to email {employee_id}: {e}")

    return {"message": "Weekly prompts sent", "notified": notified, "quarter": current_quarter}


def get_current_quarter() -> str:
    now = datetime.now(timezone.utc)
    q = (now.month - 1) // 3 + 1
    return f"{now.year}-Q{q}"


def response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, cls=DecimalEncoder),
    }
