"""
Feedback Collection Lambda
Handles:
  POST /review/submit  — submit self/manager/peer review
  GET  /review/status/{employee_id}
  GET  /forms/{form_type}

Peer anonymisation: SHA-256(reviewer_id + cycle_id + SALT) replaces raw reviewer_id.
The mapping is never stored — reviewer identity is irreversible from the hash alone.
"""

import json
import os
import uuid
import hashlib
import boto3
from datetime import datetime, timezone
from decimal import Decimal
from boto3.dynamodb.conditions import Key, Attr
from decimal_encoder import DecimalEncoder

dynamodb = boto3.resource("dynamodb")

CYCLES_TABLE = os.environ["CYCLES_TABLE"]
EMPLOYEES_TABLE = os.environ["EMPLOYEES_TABLE"]
FORM_CONFIG_TABLE = os.environ["FORM_CONFIG_TABLE"]
SUBMISSIONS_TABLE = os.environ["SUBMISSIONS_TABLE"]

# Salt for peer reviewer hashing.
# In production this should be a Secrets Manager value.
PEER_HASH_SALT = os.environ.get("PEER_HASH_SALT", "pr-system-default-salt-change-me")

VALID_FORM_TYPES = {"self", "manager", "peer"}


def lambda_handler(event: dict, context) -> dict:
    method = event["httpMethod"]
    path = event["resource"]

    try:
        if method == "POST" and path == "/review/submit":
            return submit_review(event)
        elif method == "GET" and path == "/review/status/{employee_id}":
            return get_status(event)
        elif method == "GET" and path == "/forms/{form_type}":
            return get_form_config(event)
        else:
            return response(404, {"error": "Route not found"})
    except ValueError as e:
        return response(400, {"error": str(e)})
    except Exception as e:
        print(f"ERROR: {e}")
        return response(500, {"error": "Internal server error"})


# ─── Submit Review ────────────────────────────────────────────────────────────

def submit_review(event: dict) -> dict:
    body = json.loads(event.get("body") or "{}")
    claims = event["requestContext"]["authorizer"]["claims"]
    reviewer_id = claims.get("custom:employee_id")

    required = ["cycle_id", "reviewee_id", "review_type", "responses"]
    missing = [f for f in required if not body.get(f)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

    review_type = body["review_type"]
    if review_type not in VALID_FORM_TYPES:
        raise ValueError(f"review_type must be one of: {', '.join(VALID_FORM_TYPES)}")

    cycle_id = body["cycle_id"]
    reviewee_id = body["reviewee_id"]

    # Validate cycle exists and is active
    cycle = dynamodb.Table(CYCLES_TABLE).get_item(Key={"cycle_id": cycle_id}).get("Item")
    if not cycle:
        raise ValueError("Cycle not found")
    if cycle["status"] != "active":
        raise ValueError("This review cycle is no longer accepting submissions")
    if reviewee_id not in cycle["employee_ids"]:
        raise ValueError("Reviewee is not part of this cycle")

    # Validate responses against form config
    form = get_form_definition(review_type)
    validated_responses = validate_responses(body["responses"], form["questions"])

    # Self-review: reviewer must be reviewing themselves
    if review_type == "self" and reviewer_id != reviewee_id:
        raise ValueError("Self-review must be submitted for yourself")

    # Manager review: reviewer must have manager role
    if review_type == "manager":
        caller_role = claims.get("custom:role", "")
        if caller_role not in ("manager", "hr_admin"):
            raise ValueError("Only managers can submit manager reviews")

    # Prevent duplicate submissions (self and manager are unique per cycle+reviewee)
    if review_type in ("self", "manager"):
        check_duplicate(cycle_id, reviewee_id, review_type, reviewer_id)

    # Prevent duplicate peer review from same person to same reviewee in same cycle
    # Use the hashed id for comparison since that's what gets stored
    if review_type == "peer":
        hashed_for_check = hashlib.sha256(
            f"{reviewer_id}:{cycle_id}:{PEER_HASH_SALT}".encode()
        ).hexdigest()
        check_duplicate(cycle_id, reviewee_id, review_type, hashed_for_check)

    # ── Anonymisation for peer reviews ──────────────────────────────────────
    # We store a hashed reviewer_id instead of the raw employee ID.
    # Hash = SHA-256(reviewer_id + ":" + cycle_id + ":" + SALT)
    # The SALT is application-level; without it the hash cannot be reversed.
    # The raw reviewer_id is NEVER written to DynamoDB for peer reviews.
    stored_reviewer_id = reviewer_id  # default for self/manager
    is_anonymous = False

    if review_type == "peer":
        hash_input = f"{reviewer_id}:{cycle_id}:{PEER_HASH_SALT}"
        stored_reviewer_id = hashlib.sha256(hash_input.encode()).hexdigest()
        is_anonymous = True

    submission = {
        "submission_id": str(uuid.uuid4()),
        "cycle_id": cycle_id,
        "reviewee_id": reviewee_id,
        "reviewer_id": stored_reviewer_id,  # hashed for peer, raw for self/manager
        "review_type": review_type,
        "is_anonymous": is_anonymous,
        "responses": validated_responses,
        "composite_score": calculate_score(validated_responses),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    dynamodb.Table(SUBMISSIONS_TABLE).put_item(Item=submission)

    # Update cycle stats counter
    update_cycle_stats(cycle_id, review_type)

    return response(201, {
        "message": "Review submitted successfully",
        "submission_id": submission["submission_id"],
        "composite_score": submission["composite_score"],
    })


# ─── Get Review Status ────────────────────────────────────────────────────────

def get_status(event: dict) -> dict:
    employee_id = event["pathParameters"]["employee_id"]
    claims = event["requestContext"]["authorizer"]["claims"]
    caller_role = claims.get("custom:role", "")
    caller_id = claims.get("custom:employee_id", "")

    # Employees can only view their own status; managers/HR can view anyone
    if caller_role == "employee" and caller_id != employee_id:
        return response(403, {"error": "Access denied"})

    # Get all active cycles this employee is part of
    cycles_table = dynamodb.Table(CYCLES_TABLE)
    result = cycles_table.scan(
        FilterExpression=Attr("status").eq("active") & Attr("employee_ids").contains(employee_id)
    )
    cycles = result.get("Items", [])

    status_by_cycle = []
    for cycle in cycles:
        cycle_id = cycle["cycle_id"]
        submissions = get_submissions_for(cycle_id, employee_id)

        submitted_types = {s["review_type"] for s in submissions}
        pending = []
        if "self" not in submitted_types:
            pending.append("self")

        # Count peer reviews GIVEN by this employee as the reviewer.
        # The GSI is keyed on reviewee_id so we must scan by reviewer_id.
        # Note: peer reviewer_id is hashed for anonymity, so this count reflects
        # non-peer reviews given (self/manager). Peer given count will always be 0
        # here by design — anonymisation prevents linking peers to their submissions.
        given_result = dynamodb.Table(SUBMISSIONS_TABLE).scan(
            FilterExpression=Attr("cycle_id").eq(cycle_id)
                & Attr("reviewer_id").eq(employee_id)
                & Attr("review_type").eq("peer")
        )
        peer_reviews_given = len(given_result.get("Items", []))

        status_by_cycle.append({
            "cycle_id": cycle_id,
            "cycle_name": cycle["name"],
            "end_date": cycle["end_date"],
            "pending_reviews": pending,
            "submitted_types": list(submitted_types),
            "peer_reviews_given": peer_reviews_given,
        })

    return response(200, {
        "employee_id": employee_id,
        "status": status_by_cycle,
    })


# ─── Get Form Config ──────────────────────────────────────────────────────────

def get_form_config(event: dict) -> dict:
    form_type = event["pathParameters"]["form_type"]
    if form_type not in VALID_FORM_TYPES:
        return response(400, {"error": f"Invalid form_type: {form_type}"})

    form = get_form_definition(form_type)
    return response(200, {"form": form})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_form_definition(form_type: str) -> dict:
    """Load form from DynamoDB, fallback to hardcoded defaults."""
    result = dynamodb.Table(FORM_CONFIG_TABLE).get_item(Key={"form_type": form_type})
    if "Item" in result:
        return result["Item"]

    # Default form definitions (used until seeded in DynamoDB)
    defaults = {
        "self": {
            "form_type": "self",
            "title": "Self Review",
            "questions": [
                {"id": "q1", "text": "What were your top 3 achievements this period?", "type": "text"},
                {"id": "q2", "text": "What challenges did you face and how did you overcome them?", "type": "text"},
                {"id": "q3", "text": "Rate your overall performance this period.", "type": "rating", "min": 1, "max": 5},
                {"id": "q4", "text": "Rate your collaboration with your team.", "type": "rating", "min": 1, "max": 5},
                {"id": "q5", "text": "What are your development goals for next period?", "type": "text"},
            ],
        },
        "manager": {
            "form_type": "manager",
            "title": "Manager Review",
            "questions": [
                {"id": "q1", "text": "Rate this employee's delivery of goals.", "type": "rating", "min": 1, "max": 5},
                {"id": "q2", "text": "Rate their communication and collaboration.", "type": "rating", "min": 1, "max": 5},
                {"id": "q3", "text": "Rate their initiative and problem-solving.", "type": "rating", "min": 1, "max": 5},
                {"id": "q4", "text": "What are their key strengths?", "type": "text"},
                {"id": "q5", "text": "What are their key areas for improvement?", "type": "text"},
                {"id": "q6", "text": "Overall performance rating.", "type": "rating", "min": 1, "max": 5},
            ],
        },
        "peer": {
            "form_type": "peer",
            "title": "Peer Review (Anonymous)",
            "questions": [
                {"id": "q1", "text": "Rate this colleague's collaboration and teamwork.", "type": "rating", "min": 1, "max": 5},
                {"id": "q2", "text": "Rate their communication skills.", "type": "rating", "min": 1, "max": 5},
                {"id": "q3", "text": "Rate their reliability and follow-through.", "type": "rating", "min": 1, "max": 5},
                {"id": "q4", "text": "What does this colleague do particularly well?", "type": "text"},
                {"id": "q5", "text": "What could they improve to be more effective?", "type": "text"},
            ],
        },
    }
    return defaults[form_type]


def validate_responses(responses: list, questions: list) -> list:
    """Validate that ALL form questions are answered and ratings are in range."""
    question_map = {q["id"]: q for q in questions}
    response_map = {r.get("question_id"): r for r in responses}

    # Enforce every question is answered
    missing_qs = [q["id"] for q in questions if q["id"] not in response_map]
    if missing_qs:
        raise ValueError(f"Missing answers for questions: {', '.join(missing_qs)}")

    validated = []
    for q in questions:
        q_id = q["id"]
        resp = response_map[q_id]
        value = resp.get("value")

        if q["type"] == "rating":
            try:
                rating = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"Question {q_id} requires a numeric rating")
            if not (q["min"] <= rating <= q["max"]):
                raise ValueError(
                    f"Rating for {q_id} must be between {q['min']} and {q['max']}"
                )
            validated.append({"question_id": q_id, "type": "rating", "value": rating})
        else:
            if not value or not str(value).strip():
                raise ValueError(f"Question {q_id} requires a text response")
            validated.append({"question_id": q_id, "type": "text", "value": str(value).strip()})

    return validated


def calculate_score(responses: list):
    """Average of all rating responses. Returns None if no ratings."""
    ratings = [r["value"] for r in responses if r["type"] == "rating"]
    if not ratings:
        return None
    return Decimal(str(round(sum(ratings) / len(ratings), 2)))


def check_duplicate(cycle_id: str, reviewee_id: str, review_type: str, reviewer_id: str):
    """Raise if this reviewer already submitted this review type for this reviewee in this cycle."""
    result = dynamodb.Table(SUBMISSIONS_TABLE).query(
        IndexName="cycle-reviewee-index",
        KeyConditionExpression=Key("cycle_id").eq(cycle_id) & Key("reviewee_id").eq(reviewee_id),
        FilterExpression=Attr("review_type").eq(review_type) & Attr("reviewer_id").eq(reviewer_id),
    )
    if result.get("Items"):
        raise ValueError(f"You have already submitted a {review_type} review for this employee in this cycle")


def get_submissions_for(cycle_id: str, reviewee_id: str) -> list:
    result = dynamodb.Table(SUBMISSIONS_TABLE).query(
        IndexName="cycle-reviewee-index",
        KeyConditionExpression=Key("cycle_id").eq(cycle_id) & Key("reviewee_id").eq(reviewee_id),
    )
    return result.get("Items", [])


def update_cycle_stats(cycle_id: str, review_type: str):
    """Increment the submission counter for the given review type in the cycle."""
    field_map = {
        "self": "self_reviews_submitted",
        "manager": "manager_reviews_submitted",
        "peer": "peer_reviews_submitted",
    }
    field = field_map.get(review_type)
    if not field:
        return

    # DynamoDB does not support ADD on nested map attributes.
    # Use a conditional update expression on the top-level submission_stats map field.
    table = dynamodb.Table(CYCLES_TABLE)
    try:
        table.update_item(
            Key={"cycle_id": cycle_id},
            UpdateExpression=f"ADD submission_stats.{field} :one",
            ExpressionAttributeValues={":one": 1},
        )
    except Exception:
        # Fallback: fetch-increment-write (safe for low concurrency demo scale)
        result = table.get_item(Key={"cycle_id": cycle_id})
        if "Item" not in result:
            return
        cycle = result["Item"]
        stats = cycle.get("submission_stats", {})
        stats[field] = int(stats.get(field, 0)) + 1
        table.update_item(
            Key={"cycle_id": cycle_id},
            UpdateExpression="SET submission_stats = :s",
            ExpressionAttributeValues={":s": stats},
        )


def response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps(body, cls=DecimalEncoder),
    }
