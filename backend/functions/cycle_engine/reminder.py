"""
Reminder Lambda
Called by Step Functions for:
  - notify_start   : initial notification to all participants
  - remind_3day    : 3-day deadline reminder (only to pending)
  - remind_1day    : 1-day deadline reminder (only to pending)
  - check_completion: check if all reviews done
  - close_cycle    : mark cycle as closed
"""

import json
import os
import boto3
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("ses")

CYCLES_TABLE = os.environ["CYCLES_TABLE"]
EMPLOYEES_TABLE = os.environ["EMPLOYEES_TABLE"]
SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]
SES_SENDER = os.environ["SES_SENDER_EMAIL"]


def lambda_handler(event: dict, context) -> dict:
    action = event["action"]
    cycle_id = event["cycle_id"]

    cycle = get_cycle(cycle_id)
    if not cycle:
        raise ValueError(f"Cycle not found: {cycle_id}")

    if action == "notify_start":
        return notify_start(cycle)
    elif action == "remind_3day":
        return send_reminder(cycle, days_left=3)
    elif action == "remind_1day":
        return send_reminder(cycle, days_left=1)
    elif action == "check_completion":
        return check_completion(cycle)
    elif action == "close_cycle":
        return close_cycle(cycle)
    else:
        raise ValueError(f"Unknown action: {action}")


def get_cycle(cycle_id: str) -> dict:
    result = dynamodb.Table(CYCLES_TABLE).get_item(Key={"cycle_id": cycle_id})
    return result.get("Item")


def get_employees(employee_ids: list) -> list:
    table = dynamodb.Table(EMPLOYEES_TABLE)
    employees = []
    for emp_id in employee_ids:
        result = table.get_item(Key={"employee_id": emp_id})
        if "Item" in result:
            employees.append(result["Item"])
    return employees


def get_pending_employees(cycle: dict) -> list:
    """Return employees who haven't submitted their self-review yet."""
    cycle_id = cycle["cycle_id"]
    submissions_table = dynamodb.Table(SUBMISSIONS_TABLE)

    result = submissions_table.query(
        IndexName="cycle-reviewee-index",
        KeyConditionExpression=Key("cycle_id").eq(cycle_id),
        FilterExpression=Attr("review_type").eq("self"),
    )

    submitted_ids = {item["reviewee_id"] for item in result.get("Items", [])}
    all_ids = set(cycle["employee_ids"])
    pending_ids = all_ids - submitted_ids

    return get_employees(list(pending_ids))


def send_email(to_addresses: list, subject: str, body_html: str):
    """Send SES email. In sandbox mode, only verified addresses receive mail."""
    if not to_addresses:
        return

    for address in to_addresses:
        try:
            ses.send_email(
                Source=SES_SENDER,
                Destination={"ToAddresses": [address]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Html": {"Data": body_html}},
                },
            )
        except ses.exceptions.MessageRejected as e:
            # In sandbox: unverified addresses are rejected — log and continue
            print(f"SES rejected {address}: {e}")


def notify_start(cycle: dict) -> dict:
    from datetime import datetime
    employees = get_employees(cycle["employee_ids"])
    cycle_name = cycle["name"]
    start_date = cycle["start_date"]
    end_date = cycle["end_date"]

    # Calculate days remaining
    try:
        days_left = (datetime.fromisoformat(end_date) - datetime.now()).days
    except Exception:
        days_left = None
    days_text = f"{days_left} days" if days_left is not None else end_date

    subject = f"[Performance Review] Action Required — '{cycle_name}' cycle has started"

    for emp in employees:
        email = emp.get("email")
        name = emp.get("name", "there")
        if not email:
            continue

        body = f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px;">
            <h2 style="color: #4F6EFF; margin-bottom: 4px;">Performance Review Started</h2>
            <p style="color: #6b7280; margin-top: 0;">You have {days_text} to complete your review</p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <p>Hi <strong>{name}</strong>,</p>
            <p>The <strong>{cycle_name}</strong> performance review cycle is now open and requires your participation.</p>

            <div style="background: #f3f4f6; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 12px;">
                    <span style="color: #6b7280; font-size: 13px;">Start Date</span>
                    <strong>{start_date}</strong>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 12px;">
                    <span style="color: #6b7280; font-size: 13px;">Deadline</span>
                    <strong style="color: #DC2626;">{end_date}</strong>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #6b7280; font-size: 13px;">Time Remaining</span>
                    <strong style="color: #D97706;">{days_text}</strong>
                </div>
            </div>

            <p><strong>What you need to complete:</strong></p>
            <ul style="color: #374151; line-height: 2;">
                <li>✅ <strong>Self Review</strong> — rate your own performance and answer questions</li>
                <li>✅ <strong>Peer Reviews</strong> — anonymously review your colleagues</li>
            </ul>

            <p style="color: #6b7280; font-size: 13px; margin-top: 24px;">
                You will receive reminder emails <strong>3 days</strong> and <strong>1 day</strong> before the deadline
                if your review is still pending.
            </p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="color: #9ca3af; font-size: 12px;">
                This is an automated notification from the 360° Performance Review System.
            </p>
        </div>
        """
        send_email([email], subject, body)

    return {"action": "notify_start", "notified": len(employees)}


def send_reminder(cycle: dict, days_left: int) -> dict:
    pending = get_pending_employees(cycle)
    cycle_name = cycle["name"]
    end_date = cycle["end_date"]
    urgency_color = "#DC2626" if days_left == 1 else "#D97706"
    urgency_text = "FINAL REMINDER" if days_left == 1 else "REMINDER"
    subject = f"[{urgency_text}] {days_left} day(s) left — complete your review for '{cycle_name}'"

    for emp in pending:
        email = emp.get("email")
        name = emp.get("name", "there")
        if not email:
            continue

        body = f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px;">
            <h2 style="color: {urgency_color}; margin-bottom: 4px;">
                {"⚠ " if days_left == 1 else ""}Review Deadline in {days_left} Day{"s" if days_left > 1 else ""}
            </h2>
            <p style="color: #6b7280; margin-top: 0;">{cycle_name}</p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <p>Hi <strong>{name}</strong>,</p>
            <p>{"This is your final reminder. " if days_left == 1 else ""}Your performance review is <strong>still pending</strong>
            and the deadline is <strong style="color: {urgency_color};">{end_date}</strong>.</p>

            <div style="background: {"#FEF2F2" if days_left == 1 else "#FFF7ED"}; border: 1px solid {urgency_color}; 
                border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
                <div style="font-size: 32px; font-weight: 700; color: {urgency_color};">{days_left} day{"s" if days_left > 1 else ""} left</div>
                <div style="font-size: 13px; color: #6b7280; margin-top: 4px;">Deadline: {end_date}</div>
            </div>

            <p><strong>Still needed from you:</strong></p>
            <ul style="color: #374151; line-height: 2;">
                <li>✅ <strong>Self Review</strong> — rate your own performance</li>
                <li>✅ <strong>Peer Reviews</strong> — review your colleagues anonymously</li>
            </ul>

            <p>Please log in and complete your review before the deadline.</p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="color: #9ca3af; font-size: 12px;">
                This is an automated reminder from the 360° Performance Review System.
            </p>
        </div>
        """
        send_email([email], subject, body)

    return {
        "action": f"remind_{days_left}day",
        "pending_count": len(pending),
        "notified": len(pending),
    }


def check_completion(cycle: dict) -> dict:
    cycle_id = cycle["cycle_id"]
    employee_ids = cycle["employee_ids"]

    submissions_table = dynamodb.Table(SUBMISSIONS_TABLE)
    result = submissions_table.query(
        IndexName="cycle-reviewee-index",
        KeyConditionExpression=Key("cycle_id").eq(cycle_id),
    )

    submissions = result.get("Items", [])
    self_review_ids = {
        s["reviewee_id"] for s in submissions if s.get("review_type") == "self"
    }

    all_complete = all(emp_id in self_review_ids for emp_id in employee_ids)

    return {
        "all_complete": all_complete,
        "self_reviews_done": len(self_review_ids),
        "total_employees": len(employee_ids),
    }


def close_cycle(cycle: dict) -> dict:
    dynamodb.Table(CYCLES_TABLE).update_item(
        Key={"cycle_id": cycle["cycle_id"]},
        UpdateExpression="SET #s = :s, closed_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "closed",
            ":t": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"action": "close_cycle", "cycle_id": cycle["cycle_id"]}
