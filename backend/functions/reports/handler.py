"""
Report Generation Lambda
Handles:
  POST /report/{cycle_id}/{employee_id} — generate report (HR/Manager only)
  GET  /report/{cycle_id}/{employee_id} — get presigned S3 URL to report
  GET  /dashboard/{cycle_id}            — HR dashboard: cycle stats
  action=generate_all (Step Functions)  — generate all reports at cycle close
"""

import json
import os
import uuid
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr
from decimal_encoder import DecimalEncoder

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
ses = boto3.client("ses")

CYCLES_TABLE = os.environ["CYCLES_TABLE"]
EMPLOYEES_TABLE = os.environ["EMPLOYEES_TABLE"]
SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]
OKR_TABLE = os.environ["OKR_TABLE"]
REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]
SES_SENDER = os.environ.get("SES_SENDER_EMAIL", "")

# Weights for composite score
from decimal import Decimal
WEIGHTS = {"self": Decimal("0.20"), "manager": Decimal("0.50"), "peer": Decimal("0.30")}


def lambda_handler(event: dict, context) -> dict:
    # Step Functions invocation
    if event.get("action") == "generate_all":
        return generate_all_reports(event["cycle_id"])

    method = event["httpMethod"]
    path = event["resource"]

    try:
        if method == "POST" and path == "/report/{cycle_id}/{employee_id}":
            return trigger_report(event)
        elif method == "GET" and path == "/report/{cycle_id}/{employee_id}":
            return get_report_url(event)
        elif method == "GET" and path == "/dashboard/{cycle_id}":
            return get_dashboard(event)
        elif method == "DELETE" and path == "/report/{cycle_id}":
            return delete_cycle_reports(event)
        else:
            return response(404, {"error": "Route not found"})
    except ValueError as e:
        return response(400, {"error": str(e)})
    except Exception as e:
        print(f"ERROR: {e}")
        return response(500, {"error": "Internal server error"})


# ─── Generate Report for One Employee ────────────────────────────────────────

def generate_report(cycle_id: str, employee_id: str) -> dict:
    cycle = dynamodb.Table(CYCLES_TABLE).get_item(Key={"cycle_id": cycle_id}).get("Item")
    employee = dynamodb.Table(EMPLOYEES_TABLE).get_item(Key={"employee_id": employee_id}).get("Item")

    if not cycle or not employee:
        raise ValueError("Cycle or employee not found")

    # Fetch all submissions for this employee in this cycle
    result = dynamodb.Table(SUBMISSIONS_TABLE).query(
        IndexName="cycle-reviewee-index",
        KeyConditionExpression=Key("cycle_id").eq(cycle_id) & Key("reviewee_id").eq(employee_id),
    )
    submissions = result.get("Items", [])

    # Group by review type
    by_type: dict = {"self": [], "manager": [], "peer": []}
    for sub in submissions:
        review_type = sub.get("review_type")
        if review_type in by_type:
            by_type[review_type].append(sub)

    # Calculate scores per type
    scores: dict = {}
    for review_type, subs in by_type.items():
        type_scores = [s["composite_score"] for s in subs if s.get("composite_score") is not None]
        scores[review_type] = Decimal(str(round(sum(float(x) for x in type_scores) / len(type_scores), 2))) if type_scores else None

    # Weighted composite rating
    weighted_sum = Decimal("0")
    weight_used = Decimal("0")
    for review_type, weight in WEIGHTS.items():
        if scores.get(review_type) is not None:
            weighted_sum += scores[review_type] * weight
            weight_used += weight

    composite = Decimal(str(round(float(weighted_sum) / float(weight_used), 2))) if weight_used > 0 else None

    # Fetch OKRs for current quarter
    current_quarter = get_current_quarter_for_cycle(cycle)
    okr_result = dynamodb.Table(OKR_TABLE).query(
        IndexName="employee-quarter-index",
        KeyConditionExpression=Key("employee_id").eq(employee_id) & Key("quarter").eq(current_quarter),
    )
    okrs = okr_result.get("Items", [])
    okr_completion = (
        Decimal(str(round(sum(float(o["overall_completion"]) for o in okrs) / len(okrs), 1))) if okrs else None
    )

    # Extract free-text feedback
    peer_comments = extract_comments(by_type["peer"])
    manager_comments = extract_comments(by_type["manager"])
    self_comments = extract_comments(by_type["self"])

    report_data = {
        "employee": employee,
        "cycle": cycle,
        "scores": scores,
        "composite_rating": composite,
        "okrs": okrs,
        "okr_completion": okr_completion,
        "peer_comments": peer_comments,
        "manager_comments": manager_comments,
        "self_comments": self_comments,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Render HTML and store in S3
    html = render_report_html(report_data)
    s3_key = f"reports/{cycle_id}/{employee_id}/report.html"
    s3.put_object(
        Bucket=REPORTS_BUCKET,
        Key=s3_key,
        Body=html.encode("utf-8"),
        ContentType="text/html",
    )

    return {
        "employee_id": employee_id,
        "cycle_id": cycle_id,
        "composite_rating": composite,
        "scores": scores,
        "s3_key": s3_key,
    }


def trigger_report(event: dict) -> dict:
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_role = claims.get("custom:role", "")
    if caller_role not in ("hr_admin", "manager"):
        return response(403, {"error": "Only HR Admin or Manager can generate reports"})

    cycle_id = event["pathParameters"]["cycle_id"]
    employee_id = event["pathParameters"]["employee_id"]
    result = generate_report(cycle_id, employee_id)

    # Send email notification to employee
    try:
        employee = dynamodb.Table(EMPLOYEES_TABLE).get_item(
            Key={"employee_id": employee_id}
        ).get("Item", {})
        cycle = dynamodb.Table(CYCLES_TABLE).get_item(
            Key={"cycle_id": cycle_id}
        ).get("Item", {})

        email = employee.get("email")
        name = employee.get("name", employee_id)
        cycle_name = cycle.get("name", cycle_id)
        composite = result.get("composite_rating")
        score_text = f"{composite}/5.0" if composite else "N/A"

        if email and SES_SENDER:
            ses.send_email(
                Source=SES_SENDER,
                Destination={"ToAddresses": [email]},
                Message={
                    "Subject": {"Data": f"[Performance Review] Your report is ready — {cycle_name}"},
                    "Body": {"Html": {"Data": f"""
                        <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px;">
                            <h2 style="color: #4F6EFF; margin-bottom: 8px;">Your Performance Report is Ready</h2>
                            <p>Hi <strong>{name}</strong>,</p>
                            <p>Your performance report for the <strong>{cycle_name}</strong> review cycle has been generated.</p>
                            <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
                                <div style="font-size: 13px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em;">Composite Score</div>
                                <div style="font-size: 40px; font-weight: 700; color: #4F6EFF; margin-top: 8px;">{score_text}</div>
                                <div style="font-size: 12px; color: #9ca3af; margin-top: 4px;">Self 20% + Manager 50% + Peer 30%</div>
                            </div>
                            <p>Log in to the 360° Performance Review system to view your full report — including peer feedback, manager comments, and OKR progress.</p>
                            <p style="color: #9ca3af; font-size: 12px; margin-top: 32px;">This is an automated notification. Please do not reply to this email.</p>
                        </div>
                    """}}
                }
            )
    except Exception as e:
        print(f"Email notification failed: {e}")
        # Non-fatal — report is still generated even if email fails

    return response(200, {"message": "Report generated", **result})


def get_report_url(event: dict) -> dict:
    cycle_id = event["pathParameters"]["cycle_id"]
    employee_id = event["pathParameters"]["employee_id"]
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_role = claims.get("custom:role", "")
    caller_id = claims.get("custom:employee_id", "")

    # Employees can only view their own report
    if caller_role == "employee" and caller_id != employee_id:
        return response(403, {"error": "Access denied"})

    s3_key = f"reports/{cycle_id}/{employee_id}/report.html"

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": REPORTS_BUCKET, "Key": s3_key},
            ExpiresIn=3600,
        )
        return response(200, {"report_url": url, "expires_in": 3600})
    except Exception:
        return response(404, {"error": "Report not yet generated"})


def generate_all_reports(cycle_id: str) -> dict:
    """Called by Step Functions after cycle deadline."""
    cycle = dynamodb.Table(CYCLES_TABLE).get_item(Key={"cycle_id": cycle_id}).get("Item")
    if not cycle:
        return {"error": "Cycle not found"}

    results = []
    for employee_id in cycle.get("employee_ids", []):
        try:
            result = generate_report(cycle_id, employee_id)
            results.append(result)
        except Exception as e:
            results.append({"employee_id": employee_id, "error": str(e)})

    return {"generated": len(results), "results": results}


# ─── HR Dashboard ──────────────────────────────────────────────────────────────

def get_dashboard(event: dict) -> dict:
    cycle_id = event["pathParameters"]["cycle_id"]
    claims = event["requestContext"]["authorizer"]["claims"]
    if claims.get("custom:role") != "hr_admin":
        return response(403, {"error": "HR Admin only"})

    cycle = dynamodb.Table(CYCLES_TABLE).get_item(Key={"cycle_id": cycle_id}).get("Item")
    if not cycle:
        return response(404, {"error": "Cycle not found"})

    employee_ids = cycle.get("employee_ids", [])
    total = len(employee_ids)

    # Query all submissions for this cycle across all reviewees
    # cycle-reviewee-index PK=cycle_id returns all items for the cycle
    submissions_result = dynamodb.Table(SUBMISSIONS_TABLE).query(
        IndexName="cycle-reviewee-index",
        KeyConditionExpression=Key("cycle_id").eq(cycle_id),
    )
    submissions = submissions_result.get("Items", [])

    # Self-reviews submitted
    self_submitted = {s["reviewee_id"] for s in submissions if s["review_type"] == "self"}
    no_reviews = [eid for eid in employee_ids if eid not in self_submitted]

    # Fetch all employee records for department grouping
    emp_table = dynamodb.Table(EMPLOYEES_TABLE)
    emp_records = {}
    for eid in employee_ids:
        result = emp_table.get_item(Key={"employee_id": eid})
        if "Item" in result:
            emp_records[eid] = result["Item"]

    # Average ratings by review type (overall)
    avg_ratings: dict = {}
    for review_type in ("self", "manager", "peer"):
        type_scores = [
            s["composite_score"]
            for s in submissions
            if s["review_type"] == review_type and s.get("composite_score") is not None
        ]
        avg_ratings[review_type] = Decimal(str(round(sum(float(x) for x in type_scores) / len(type_scores), 2))) if type_scores else None

    # Average ratings by department/team
    # Groups composite scores of all reviews received by employees in each department
    dept_scores: dict = {}
    for s in submissions:
        if s.get("composite_score") is None:
            continue
        emp = emp_records.get(s["reviewee_id"])
        if not emp:
            continue
        dept = emp.get("department", "Unknown")
        dept_scores.setdefault(dept, []).append(s["composite_score"])

    ratings_by_team = {
        dept: round(sum(scores) / len(scores), 2)
        for dept, scores in dept_scores.items()
    }

    # Per-employee completion (with name and department for UI)
    employee_status = []
    for eid in employee_ids:
        emp = emp_records.get(eid, {})
        emp_subs = [s for s in submissions if s["reviewee_id"] == eid]
        emp_types = {s["review_type"] for s in emp_subs}
        # Weighted composite if all review types present
        type_scores = {}
        for rt in ("self", "manager", "peer"):
            rt_scores = [s["composite_score"] for s in emp_subs if s["review_type"] == rt and s.get("composite_score") is not None]
            type_scores[rt] = round(sum(rt_scores) / len(rt_scores), 2) if rt_scores else None

        weighted_sum, weight_used = Decimal("0"), Decimal("0")
        for rt, w in WEIGHTS.items():
            if type_scores.get(rt) is not None:
                weighted_sum += type_scores[rt] * w
                weight_used += w
        composite = Decimal(str(round(float(weighted_sum) / float(weight_used), 2))) if weight_used > 0 else None

        employee_status.append({
            "employee_id": eid,
            "name": emp.get("name", eid),
            "department": emp.get("department", "Unknown"),
            "role": emp.get("role", ""),
            "self_submitted": "self" in emp_types,
            "manager_submitted": "manager" in emp_types,
            "peer_count": len([s for s in emp_subs if s["review_type"] == "peer"]),
            "composite_rating": composite,
        })

    completion_rate = round(len(self_submitted) / total * 100, 1) if total else 0

    return response(200, {
        "cycle_id": cycle_id,
        "cycle_name": cycle["name"],
        "cycle_status": cycle["status"],
        "total_employees": total,
        "completion_rate": completion_rate,
        "self_reviews_submitted": len(self_submitted),
        "no_reviews_submitted": no_reviews,
        "average_ratings": avg_ratings,           # overall by review type
        "ratings_by_team": ratings_by_team,       # grouped by department
        "employee_status": employee_status,
    })


# ─── HTML Report Renderer ─────────────────────────────────────────────────────

def render_report_html(data: dict) -> str:
    emp = data["employee"]
    cycle = data["cycle"]
    scores = data["scores"]
    composite = data["composite_rating"]
    okrs = data["okrs"]
    peer_comments = data["peer_comments"]
    manager_comments = data["manager_comments"]
    generated_at = data["generated_at"]

    def score_badge(score):
        if score is None:
            return '<span style="color:#aaa">N/A</span>'
        color = "#22c55e" if score >= 4 else "#f59e0b" if score >= 3 else "#ef4444"
        return f'<span style="color:{color};font-weight:bold">{score}/5</span>'

    def okr_bar(pct):
        color = "#22c55e" if pct >= 70 else "#f59e0b" if pct >= 40 else "#ef4444"
        return f"""
        <div style="background:#e5e7eb;border-radius:4px;height:12px;width:100%">
          <div style="background:{color};width:{pct}%;height:12px;border-radius:4px"></div>
        </div>"""

    peer_html = "".join(
        f'<li style="margin-bottom:8px;color:#374151">"{c}"</li>'
        for c in peer_comments
    ) or "<li style='color:#aaa'>No peer comments</li>"

    manager_html = "".join(
        f'<li style="margin-bottom:8px;color:#374151">"{c}"</li>'
        for c in manager_comments
    ) or "<li style='color:#aaa'>No manager comments</li>"

    okr_html = ""
    for okr in okrs:
        krs_html = "".join(
            f"""<tr>
              <td style="padding:8px;border-bottom:1px solid #f3f4f6">{kr['title']}</td>
              <td style="padding:8px;border-bottom:1px solid #f3f4f6">{kr['target_metric']}</td>
              <td style="padding:8px;border-bottom:1px solid #f3f4f6;width:120px">
                {okr_bar(kr['progress'])}
                <small>{kr['progress']}%</small>
              </td>
            </tr>"""
            for kr in okr["key_results"]
        )
        okr_html += f"""
        <div style="margin-bottom:24px;border:1px solid #e5e7eb;border-radius:8px;padding:16px">
          <h4 style="margin:0 0 12px;color:#1f2937">{okr['objective_title']}</h4>
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="background:#f9fafb">
                <th style="padding:8px;text-align:left;font-size:12px;color:#6b7280">KEY RESULT</th>
                <th style="padding:8px;text-align:left;font-size:12px;color:#6b7280">TARGET</th>
                <th style="padding:8px;text-align:left;font-size:12px;color:#6b7280">PROGRESS</th>
              </tr>
            </thead>
            <tbody>{krs_html}</tbody>
          </table>
          <div style="margin-top:12px">
            <strong>Overall: {okr['overall_completion']}%</strong>
            {okr_bar(okr['overall_completion'])}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Performance Report — {emp.get('name', emp['employee_id'])}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 40px; color: #111; background: #f9fafb; }}
    .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    h1 {{ font-size: 28px; margin: 0 0 4px; }} h2 {{ font-size: 20px; color: #374151; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
    .score-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
    .score-box {{ text-align: center; padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px; }}
    .score-box .label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; }}
    .score-box .value {{ font-size: 32px; font-weight: 700; margin: 8px 0 0; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
    .badge-active {{ background: #dcfce7; color: #166534; }}
    footer {{ text-align: center; color: #9ca3af; font-size: 12px; margin-top: 40px; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:start">
      <div>
        <h1>{emp.get('name', emp['employee_id'])}</h1>
        <p style="color:#6b7280;margin:4px 0">{emp.get('role', '')} · {emp.get('department', '')}</p>
        <span class="badge badge-active">{cycle['name']}</span>
      </div>
      <div style="text-align:right;color:#6b7280;font-size:13px">
        <div>Review period: {cycle['start_date']} – {cycle['end_date']}</div>
        <div>Generated: {generated_at[:10]}</div>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Performance Scores</h2>
    <div class="score-grid" style="margin-top:16px">
      <div class="score-box">
        <div class="label">Composite Rating</div>
        <div class="value" style="color:{'#22c55e' if composite and composite>=4 else '#f59e0b' if composite and composite>=3 else '#ef4444'}">{composite or 'N/A'}</div>
        <div style="font-size:12px;color:#6b7280">out of 5.0</div>
      </div>
      <div class="score-box">
        <div class="label">Self Review (20%)</div>
        <div class="value">{score_badge(scores.get('self'))}</div>
      </div>
      <div class="score-box">
        <div class="label">Manager Review (50%)</div>
        <div class="value">{score_badge(scores.get('manager'))}</div>
      </div>
      <div class="score-box">
        <div class="label">Peer Reviews (30%)</div>
        <div class="value">{score_badge(scores.get('peer'))}</div>
      </div>
    </div>
    <p style="font-size:12px;color:#9ca3af;margin-top:16px">
      Weighted composite: Self×20% + Manager×50% + Peer×30%
    </p>
  </div>

  <div class="card">
    <h2>OKR Progress</h2>
    {okr_html if okr_html else '<p style="color:#aaa">No OKRs found for this period.</p>'}
  </div>

  <div class="card">
    <h2>Manager Feedback</h2>
    <ul style="padding-left:20px;line-height:1.8">{manager_html}</ul>
  </div>

  <div class="card">
    <h2>Anonymous Peer Feedback</h2>
    <p style="font-size:12px;color:#6b7280">Peer reviewer identities are protected by one-way hashing and are not disclosed.</p>
    <ul style="padding-left:20px;line-height:1.8">{peer_html}</ul>
  </div>

  <footer>Confidential · Generated by 360° Performance Review System · {generated_at[:10]}</footer>
</body>
</html>"""


# ─── Delete All Reports for a Cycle ──────────────────────────────────────────

def delete_cycle_reports(event: dict) -> dict:
    """Delete all S3 report files for a cycle when cycle is deleted."""
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_role = claims.get("custom:role", "")
    if caller_role != "hr_admin":
        return response(403, {"error": "Only HR Admin can delete cycle reports"})

    cycle_id = event["pathParameters"]["cycle_id"]

    # List all objects under reports/{cycle_id}/
    prefix = f"reports/{cycle_id}/"
    try:
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=REPORTS_BUCKET, Prefix=prefix)

        objects_to_delete = []
        for page in pages:
            for obj in page.get("Contents", []):
                objects_to_delete.append({"Key": obj["Key"]})

        if objects_to_delete:
            s3.delete_objects(
                Bucket=REPORTS_BUCKET,
                Delete={"Objects": objects_to_delete}
            )

        return response(200, {
            "message": f"Deleted {len(objects_to_delete)} report file(s) for cycle {cycle_id}",
            "deleted_count": len(objects_to_delete)
        })
    except Exception as e:
        print(f"S3 cleanup error: {e}")
        return response(500, {"error": "Failed to delete reports from S3"})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_comments(submissions: list) -> list:
    comments = []
    for sub in submissions:
        for resp in sub.get("responses", []):
            if resp.get("type") == "text" and resp.get("value"):
                comments.append(resp["value"])
    return comments


def get_current_quarter_for_cycle(cycle: dict) -> str:
    try:
        dt = datetime.fromisoformat(cycle["start_date"])
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}-Q{q}"
    except Exception:
        now = datetime.now(timezone.utc)
        q = (now.month - 1) // 3 + 1
        return f"{now.year}-Q{q}"


def response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, cls=DecimalEncoder),
    }
