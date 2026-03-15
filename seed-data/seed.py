"""
Seed script — run locally with:
  python seed.py --env dev --region us-east-1

Populates:
  - employees table (3 employees, 1 manager, 1 HR admin)
  - form_config table (self, manager, peer questions)
  - Creates one sample OKR per employee
"""

import argparse
import boto3
import uuid
import json
from datetime import datetime, timezone
from decimal import Decimal

parser = argparse.ArgumentParser()
parser.add_argument("--env", default="dev")
parser.add_argument("--region", default="us-east-1")
parser.add_argument("--user-pool-id", default=None, dest="user_pool_id",
                    help="Cognito User Pool ID (auto-fetched from CloudFormation if not provided)")
args = parser.parse_args()

dynamodb = boto3.resource("dynamodb", region_name=args.region)

CYCLES_TABLE = f"review_cycles_{args.env}"
EMPLOYEES_TABLE = f"employees_{args.env}"
FORM_CONFIG_TABLE = f"form_config_{args.env}"
OKR_TABLE = f"okr_tracker_{args.env}"

# ─── Sample Employees ─────────────────────────────────────────────────────────

EMPLOYEES = [
    {
        "employee_id": "emp-001",
        "name": "Aisha Patel",
        "email": "adilk3682@gmail.com",       # Must be verified in SES sandbox
        "role": "Software Engineer",
        "department": "Engineering",
        "cognito_role": "employee",
        "manager_id": "mgr-001",
    },
    {
        "employee_id": "emp-002",
        "name": "Rohan Desai",
        "email": "adilk81054@gmail.com",
        "role": "Product Designer",
        "department": "Design",
        "cognito_role": "employee",
        "manager_id": "mgr-001",
    },
    {
        "employee_id": "emp-003",
        "name": "Priya Sharma",
        "email": "tariyonlannister3682@gmail.com",
        "role": "Data Analyst",
        "department": "Engineering",
        "cognito_role": "employee",
        "manager_id": "mgr-001",
    },
    {
        "employee_id": "mgr-001",
        "name": "Vikram Nair",
        "email": "davidjohncena12@gmail.com",
        "role": "Engineering Manager",
        "department": "Engineering",
        "cognito_role": "manager",
        "manager_id": None,
    },
    {
        "employee_id": "hr-001",
        "name": "HR Admin",
        "email": "oggyk81054@gmail.com",
        "role": "HR Manager",
        "department": "HR",
        "cognito_role": "hr_admin",
        "manager_id": None,
    },
]

# ─── Form Questions ───────────────────────────────────────────────────────────

FORMS = [
    {
        "form_type": "self",
        "title": "Self Review",
        "description": "Reflect honestly on your performance this period.",
        "questions": [
            {"id": "q1", "text": "What were your top 3 achievements this period?", "type": "text"},
            {"id": "q2", "text": "What challenges did you face and how did you handle them?", "type": "text"},
            {"id": "q3", "text": "Rate your overall performance this period.", "type": "rating", "min": 1, "max": 5},
            {"id": "q4", "text": "Rate your collaboration and teamwork.", "type": "rating", "min": 1, "max": 5},
            {"id": "q5", "text": "Rate your communication effectiveness.", "type": "rating", "min": 1, "max": 5},
            {"id": "q6", "text": "What are your key development goals for next period?", "type": "text"},
        ],
    },
    {
        "form_type": "manager",
        "title": "Manager Review",
        "description": "Evaluate your direct report's performance this period.",
        "questions": [
            {"id": "q1", "text": "Rate this employee's delivery of goals and commitments.", "type": "rating", "min": 1, "max": 5},
            {"id": "q2", "text": "Rate their collaboration and team contribution.", "type": "rating", "min": 1, "max": 5},
            {"id": "q3", "text": "Rate their initiative and problem-solving ability.", "type": "rating", "min": 1, "max": 5},
            {"id": "q4", "text": "Rate their communication and stakeholder management.", "type": "rating", "min": 1, "max": 5},
            {"id": "q5", "text": "Overall performance rating for this period.", "type": "rating", "min": 1, "max": 5},
            {"id": "q6", "text": "What are their key strengths?", "type": "text"},
            {"id": "q7", "text": "What are their primary areas for development?", "type": "text"},
            {"id": "q8", "text": "Any additional comments or context?", "type": "text"},
        ],
    },
    {
        "form_type": "peer",
        "title": "Peer Review (Anonymous)",
        "description": "Your identity will not be disclosed. Please be honest and constructive.",
        "questions": [
            {"id": "q1", "text": "Rate this colleague's collaboration and teamwork.", "type": "rating", "min": 1, "max": 5},
            {"id": "q2", "text": "Rate their communication and responsiveness.", "type": "rating", "min": 1, "max": 5},
            {"id": "q3", "text": "Rate their reliability and follow-through on commitments.", "type": "rating", "min": 1, "max": 5},
            {"id": "q4", "text": "What does this colleague do particularly well?", "type": "text"},
            {"id": "q5", "text": "What could they do to be more effective in their role?", "type": "text"},
        ],
    },
]

# ─── Sample OKRs ─────────────────────────────────────────────────────────────

def make_okrs(quarter: str) -> list:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "okr_id": str(uuid.uuid4()),
            "employee_id": "emp-001",
            "objective_title": "Ship the new authentication module",
            "quarter": quarter,
            "key_results": [
                {"kr_id": "kr-a1", "title": "Complete OAuth 2.0 integration", "target_metric": "100% done", "progress": 80, "progress_history": [{"progress": Decimal("40"), "notes": "In progress", "recorded_at": now}, {"progress": Decimal("80"), "notes": "Almost done", "recorded_at": now}], "notes": ""},
                {"kr_id": "kr-a2", "title": "Achieve 99.9% uptime post-deploy", "target_metric": "99.9%", "progress": 60, "progress_history": [], "notes": ""},
                {"kr_id": "kr-a3", "title": "Zero P0 security bugs in pen test", "target_metric": "0 bugs", "progress": 50, "progress_history": [], "notes": ""},
            ],
            "overall_completion": Decimal("63.3"),
            "created_at": now,
            "updated_at": now,
        },
        {
            "okr_id": str(uuid.uuid4()),
            "employee_id": "emp-002",
            "objective_title": "Redesign the onboarding experience",
            "quarter": quarter,
            "key_results": [
                {"kr_id": "kr-b1", "title": "Conduct 10 user interviews", "target_metric": "10 interviews", "progress": 100, "progress_history": [], "notes": "Done"},
                {"kr_id": "kr-b2", "title": "Deliver high-fidelity mockups", "target_metric": "3 flows done", "progress": 75, "progress_history": [], "notes": ""},
            ],
            "overall_completion": Decimal("87.5"),
            "created_at": now,
            "updated_at": now,
        },
        {
            "okr_id": str(uuid.uuid4()),
            "employee_id": "emp-003",
            "objective_title": "Build automated reporting pipeline",
            "quarter": quarter,
            "key_results": [
                {"kr_id": "kr-c1", "title": "Reduce report generation time by 80%", "target_metric": "< 5 min", "progress": 40, "progress_history": [], "notes": ""},
                {"kr_id": "kr-c2", "title": "Onboard 3 teams to new dashboards", "target_metric": "3 teams", "progress": 33, "progress_history": [], "notes": ""},
            ],
            "overall_completion": Decimal("36.5"),
            "created_at": now,
            "updated_at": now,
        },
    ]


# ─── Seed ─────────────────────────────────────────────────────────────────────

def seed():
    # Employees
    emp_table = dynamodb.Table(EMPLOYEES_TABLE)
    for emp in EMPLOYEES:
        emp_table.put_item(Item=emp)
        print(f"  ✓ Employee: {emp['name']} ({emp['cognito_role']})")

    # Forms
    form_table = dynamodb.Table(FORM_CONFIG_TABLE)
    for form in FORMS:
        form_table.put_item(Item=form)
        print(f"  ✓ Form config: {form['form_type']}")

    # OKRs
    now = datetime.now(timezone.utc)
    q = (now.month - 1) // 3 + 1
    quarter = f"{now.year}-Q{q}"
    okr_table = dynamodb.Table(OKR_TABLE)
    for okr in make_okrs(quarter):
        okr_table.put_item(Item=okr)
        print(f"  ✓ OKR: {okr['objective_title']} ({okr['employee_id']})")

    print(f"\nSeed complete. Quarter seeded: {quarter}")

    # ── Cognito user creation ─────────────────────────────────────────────────
    print("\n" + "="*60)
    print("Creating Cognito users...")
    print("="*60)
    cognito = boto3.client("cognito-idp", region_name=args.region)

    # Fetch the User Pool ID from CloudFormation stack outputs
    cfn = boto3.client("cloudformation", region_name=args.region)
    stack_name = f"performance-review-system"   # adjust if you used a different stack name
    user_pool_id = None
    try:
        stacks = cfn.describe_stacks(StackName=stack_name)
        for output in stacks["Stacks"][0].get("Outputs", []):
            if output["OutputKey"] == "UserPoolId":
                user_pool_id = output["OutputValue"]
                break
    except Exception as e:
        print(f"  Could not auto-fetch User Pool ID from stack '{stack_name}': {e}")
        print("  Pass --user-pool-id manually: python seed.py --env dev --user-pool-id us-east-1_XXXXX")

    if args.user_pool_id:
        user_pool_id = args.user_pool_id

    if not user_pool_id:
        print("\n  Skipping Cognito user creation — no User Pool ID found.")
        print("  Re-run with: python seed.py --env dev --user-pool-id <your-pool-id>")
        print("\n  Or create users manually with these aws cli commands:")
        for emp in EMPLOYEES:
            print(f"\n  aws cognito-idp admin-create-user \\")
            print(f"    --user-pool-id <YOUR_POOL_ID> \\")
            print(f"    --username {emp['email']} \\")
            print(f"    --temporary-password 'TempPass1!' \\")
            print(f"    --user-attributes Name=email,Value={emp['email']} Name=email_verified,Value=true \\")
            print(f"      Name=custom:role,Value={emp['cognito_role']} Name=custom:employee_id,Value={emp['employee_id']}")
        return

    DEFAULT_TEMP_PASSWORD = "TempPass1!"
    for emp in EMPLOYEES:
        try:
            cognito.admin_create_user(
                UserPoolId=user_pool_id,
                Username=emp["email"],
                TemporaryPassword=DEFAULT_TEMP_PASSWORD,
                MessageAction="SUPPRESS",   # don't send welcome email
                UserAttributes=[
                    {"Name": "email",            "Value": emp["email"]},
                    {"Name": "email_verified",   "Value": "true"},
                    {"Name": "custom:role",      "Value": emp["cognito_role"]},
                    {"Name": "custom:employee_id", "Value": emp["employee_id"]},
                ],
            )
            # Set permanent password so users don't need to change on first login
            cognito.admin_set_user_password(
                UserPoolId=user_pool_id,
                Username=emp["email"],
                Password=DEFAULT_TEMP_PASSWORD,
                Permanent=True,
            )
            print(f"  ✓ Cognito user: {emp['email']} (role={emp['cognito_role']})")
        except cognito.exceptions.UsernameExistsException:
            print(f"  ⚠ Already exists: {emp['email']} (skipped)")
        except Exception as e:
            print(f"  ✗ Failed to create {emp['email']}: {e}")

    print(f"\n  All users created with password: {DEFAULT_TEMP_PASSWORD}")
    print("  Change passwords after first login in production!")


if __name__ == "__main__":
    print(f"Seeding environment: {args.env} | Region: {args.region}\n")
    seed()
