# 360° Performance Review & OKR Tracking System

A fully serverless AWS application for running end-to-end 360-degree employee performance reviews with automated email notifications, weighted scoring, HTML report generation, and OKR (goal) tracking.

---

## What It Does

- **HR Admin** creates a review cycle, selects employees via checkbox UI, and sets a deadline
- **Employees** submit self-reviews and anonymous peer reviews
- **Managers** submit manager reviews for their team
- **AWS automatically** sends emails at cycle start, 3 days before deadline, and 1 day before deadline
- **Composite scores** are calculated as: Self × 20% + Manager × 50% + Peer average × 30%
- **HTML reports** are generated and stored in S3, emailed to employees when ready
- **OKRs** (Objectives & Key Results) are tracked per employee with weekly automated progress reminders every Monday at 9am UTC

---

## Architecture

```
React SPA (Vite)
      ↓ HTTPS + Cognito JWT
API Gateway (REST) — 12 endpoints
      ↓
Lambda (Python 3.11) — 5 functions
      ↓
DynamoDB (5 tables) + S3 (reports)
      ↓
Step Functions — review workflow automation
EventBridge — weekly OKR reminders
SES — all email notifications
```

### AWS Services

| Service | Role |
|---|---|
| **Lambda (5)** | cycle-engine · feedback · okr · report-generator · reminder |
| **API Gateway** | 12 REST endpoints protected by Cognito JWT |
| **DynamoDB (5)** | review_cycles · employees · review_submissions · okr_tracker · form_config |
| **Cognito** | Authentication — roles: hr_admin, manager, employee |
| **S3** | Stores generated HTML reports (auto-deleted when cycle is deleted) |
| **Step Functions** | Notify → 3-day reminder → 1-day reminder → close cycle |
| **EventBridge** | Fires every Monday 9am UTC → OKR progress reminder emails |
| **SES** | All emails — cycle start, reminders, report ready, OKR prompts |
| **SAM/CloudFormation** | Entire infrastructure as code in `template.yaml` |

---

## Project Structure

```
performance-review-system/
├── infrastructure/
│   └── template.yaml              # AWS SAM template — entire stack
├── backend/
│   └── functions/
│       ├── cycle_engine/
│       │   ├── handler.py         # POST/GET/DELETE /cycles, GET /employees
│       │   └── reminder.py        # Step Functions tasks + SES emails
│       ├── feedback/
│       │   └── handler.py         # POST /review/submit, GET /review/status, GET /forms
│       ├── okr/
│       │   └── handler.py         # OKR CRUD + weekly EventBridge trigger
│       └── reports/
│           └── handler.py         # Report generation + HR dashboard + S3 cleanup
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Full React SPA — all pages, auth, routing
│   │   └── main.jsx
│   ├── .env.example               # Frontend environment variable template
│   ├── package.json
│   └── vite.config.js
├── seed-data/
│   └── seed.py                    # Seeds DynamoDB + creates Cognito users automatically
├── docs/
│   ├── anonymisation.md           # How peer reviewer identity is protected
│   └── dynamodb-schema.md         # Table designs and GSI access patterns
└── start.sh                       # One-command setup script
```

---

## Quick Start

### Prerequisites

| Tool | Install |
|---|---|
| AWS CLI | `brew install awscli` then `aws configure` |
| AWS SAM CLI | `brew install aws-sam-cli` |
| Python 3.11+ | `brew install python@3.11` |
| Node.js 18+ | `brew install node` |

### One-command setup

```bash
chmod +x start.sh && ./start.sh
```

The script automatically:
1. Checks all prerequisites
2. Verifies SES sender email (sends verification link if needed)
3. Detects if stack already deployed — skips if already up
4. Runs `sam build && sam deploy --guided` if needed
5. Fetches stack outputs and writes `frontend/.env` automatically
6. Seeds DynamoDB + creates all 5 Cognito login accounts
7. Runs `npm install && npm run dev` and prints all credentials

### Manual setup (if preferred)

```bash
# 1. Verify sender email in SES
aws ses verify-email-identity --email-address your@email.com --region ap-south-1

# 2. Deploy infrastructure
cd infrastructure
sam build
sam deploy --guided
# Stack: performance-review-system | Region: ap-south-1
# SESSourceEmail: your@email.com
# PeerHashSalt: $(openssl rand -hex 32)  ← save this!
# Environment: dev | Answer Y to all prompts

# 3. Configure frontend
cd ../frontend
cp .env.example .env
# Edit .env with ApiEndpoint, UserPoolId, UserPoolClientId from SAM outputs

# 4. Seed database
cd ../seed-data
python3 -m venv venv && source venv/bin/activate
pip install boto3
python3 seed.py --env dev --region ap-south-1

# 5. Run app
cd ../frontend
npm install && npm run dev
# Open http://localhost:3000
```

---

## Login Credentials

> All accounts use password: **TempPass1!**

| Email | Role | Employee ID | Access |
|---|---|---|---|
| `oggyk81054@gmail.com` | HR Admin | hr-001 | Create/delete cycles · full dashboard · all reports |
| `davidjohncena12@gmail.com` | Manager | mgr-001 | Manager reviews · generate & download reports · view OKRs |
| `adilk3682@gmail.com` | Employee | emp-001 | Self & peer reviews · OKR tracker · view own report |
| `adilk81054@gmail.com` | Employee | emp-002 | Self & peer reviews · OKR tracker · view own report |
| `tariyonlannister3682@gmail.com` | Employee | emp-003 | Self & peer reviews · OKR tracker · view own report |

---

## API Endpoints

All endpoints require `Authorization: Bearer <Cognito JWT>` header.

| Method | Path | Who | Description |
|---|---|---|---|
| `POST` | `/cycles` | hr_admin | Create review cycle |
| `GET` | `/cycles` | all | List cycles |
| `GET` | `/cycles/{id}` | all | Get cycle detail |
| `DELETE` | `/cycles/{id}` | hr_admin | Delete cycle + S3 reports |
| `GET` | `/employees` | hr_admin | List all employees |
| `POST` | `/review/submit` | all | Submit self/manager/peer review |
| `GET` | `/review/status/{employee_id}` | all | Get review status |
| `GET` | `/forms/{form_type}` | all | Get form questions |
| `POST` | `/okr` | all | Create OKR |
| `PUT` | `/okr/{id}` | owner | Update KR progress |
| `GET` | `/okr/employee/{employee_id}` | owner/manager/hr | Get OKRs |
| `POST` | `/report/{cycle}/{employee}` | manager/hr | Generate report |
| `GET` | `/report/{cycle}/{employee}` | owner/manager/hr | Get report URL |
| `DELETE` | `/report/{cycle_id}` | hr_admin | Delete all reports for cycle |
| `GET` | `/dashboard/{cycle_id}` | hr_admin | HR dashboard |

---

## Email Notifications

The system sends automated emails via AWS SES at these points:

| Trigger | Recipients | Content |
|---|---|---|
| Cycle created | All employees in cycle | Deadline, days remaining, what to complete |
| 3 days before deadline | Employees who haven't submitted | Urgent reminder with deadline |
| 1 day before deadline | Employees who haven't submitted | Final reminder in red |
| Report generated | The reviewed employee | Composite score + link to log in |
| Every Monday 9am UTC | All employees with incomplete OKRs | OKR progress update prompt |

> **SES Sandbox:** In sandbox mode, all recipient email addresses must be verified in SES. Request SES production access for real-world use.

---

## Scoring Formula

```
Composite Score = (Self Review × 20%) + (Manager Review × 50%) + (Peer Average × 30%)
```

If a review type has no submissions, its weight is redistributed proportionally.

---

## Peer Anonymisation

Peer reviewer identities are protected using one-way SHA-256 hashing:

```
stored_reviewer_id = SHA-256(reviewer_id + ":" + cycle_id + ":" + SALT)
```

The raw `reviewer_id` is **never written to DynamoDB** for peer reviews. The salt (`PeerHashSalt`) is set at deploy time and stored as a CloudFormation parameter with `NoEcho: true`.

See [`docs/anonymisation.md`](docs/anonymisation.md) for full details.

---

## Role-Based Access Control

| Feature | HR Admin | Manager | Employee |
|---|---|---|---|
| Create review cycle | ✅ | ❌ | ❌ |
| Delete review cycle | ✅ | ❌ | ❌ |
| View all cycles | ✅ All | ✅ All | Only assigned |
| Submit self review | ❌ | ❌ | ✅ |
| Submit manager review | ✅ | ✅ | ❌ |
| Submit peer review | ❌ | ❌ | ✅ |
| View HR dashboard | ✅ | ❌ | ❌ |
| Generate reports | ✅ | ✅ | ❌ |
| View own report | ❌ | ❌ | ✅ |
| View employee OKRs | ✅ All | ✅ All | Own only |

---

## DynamoDB Tables

| Table | Primary Key | GSI |
|---|---|---|
| `review_cycles_dev` | `cycle_id` | `status-start_date-index` |
| `employees_dev` | `employee_id` | `department-index` |
| `form_config_dev` | `form_type` | — |
| `review_submissions_dev` | `submission_id` | `cycle-reviewee-index` |
| `okr_tracker_dev` | `okr_id` | `employee-quarter-index` |

See [`docs/dynamodb-schema.md`](docs/dynamodb-schema.md) for full schema details.

---

## Development

### Updating Lambda functions without full redeploy

```bash
# Push a single Lambda directly (faster than sam deploy)
cd backend/functions/reports
zip -r /tmp/reports.zip .
aws lambda update-function-code \
  --function-name report-generator-dev \
  --zip-file fileb:///tmp/reports.zip \
  --region ap-south-1
```

### Viewing Lambda logs

```bash
aws logs tail /aws/lambda/report-generator-dev --region ap-south-1 --since 10m
aws logs tail /aws/lambda/feedback-dev --region ap-south-1 --since 10m
aws logs tail /aws/lambda/reminder-dev --region ap-south-1 --since 10m
aws logs tail /aws/lambda/okr-dev --region ap-south-1 --since 10m
aws logs tail /aws/lambda/cycle-engine-dev --region ap-south-1 --since 10m
```

### Re-seeding the database

```bash
cd seed-data
source venv/bin/activate
python3 seed.py --env dev --region ap-south-1
```

### Checking Step Functions executions

```bash
aws stepfunctions list-executions \
  --state-machine-arn arn:aws:states:ap-south-1:ACCOUNT_ID:stateMachine:ReviewCycleWorkflow-dev \
  --region ap-south-1 \
  --max-results 5
```

---

## Tear Down

Delete all AWS resources to stop any charges:

```bash
aws cloudformation delete-stack \
  --stack-name performance-review-system \
  --region ap-south-1
```

This deletes all Lambdas, DynamoDB tables, Cognito user pool, S3 bucket, API Gateway, Step Functions, and EventBridge rules.

> **Note:** The S3 bucket must be empty before deletion. If you have generated reports, delete all cycles first through the app (which auto-cleans S3) before tearing down.

---

## Security Notes

- `PeerHashSalt` is stored as `NoEcho` in CloudFormation — never visible after deploy. Save it securely.
- All API endpoints are protected by Cognito JWT — no unauthenticated access
- Peer reviewer identities are irreversibly hashed — cannot be de-anonymised without the salt
- SES is in sandbox mode by default — request production access for real users
- Change all default passwords (`TempPass1!`) before sharing with real users
- Enable Cognito MFA for production: AWS Console → Cognito → User Pool → MFA settings

---

## Built With

- **Frontend:** React 18, Vite, amazon-cognito-identity-js
- **Backend:** Python 3.11, boto3, AWS Lambda
- **Infrastructure:** AWS SAM, CloudFormation
- **Database:** Amazon DynamoDB (PAY_PER_REQUEST)
- **Auth:** Amazon Cognito
- **Email:** Amazon SES
- **Storage:** Amazon S3
- **Orchestration:** AWS Step Functions, EventBridge