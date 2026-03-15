# DynamoDB Schema Reference

## Tables Overview

| Table | Partition Key | Sort Key | GSIs |
|---|---|---|---|
| `review_cycles_{env}` | `cycle_id` (S) | — | `status-start_date-index` |
| `employees_{env}` | `employee_id` (S) | — | `department-index` |
| `form_config_{env}` | `form_type` (S) | — | — |
| `review_submissions_{env}` | `submission_id` (S) | — | `cycle-reviewee-index` |
| `okr_tracker_{env}` | `okr_id` (S) | — | `employee-quarter-index` |

---

## Table: review_cycles

**Access patterns:**
- Get cycle by ID → PK lookup on `cycle_id`
- List all active cycles → GSI scan on `status = "active"`
- List cycles by start date → GSI on `status` + `start_date` range

```json
{
  "cycle_id": "uuid-string",
  "name": "Q4 2025 Performance Review",
  "start_date": "2025-10-01",
  "end_date": "2025-11-30",
  "employee_ids": ["emp-001", "emp-002", "emp-003"],
  "status": "active | closed",
  "created_by": "hr-001",
  "created_at": "2025-10-01T00:00:00Z",
  "closed_at": "2025-12-01T00:00:00Z",
  "submission_stats": {
    "total_employees": 3,
    "self_reviews_submitted": 2,
    "manager_reviews_submitted": 2,
    "peer_reviews_submitted": 6
  }
}
```

---

## Table: employees

**Access patterns:**
- Get employee by ID → PK lookup
- List employees by department → GSI on `department`

```json
{
  "employee_id": "emp-001",
  "name": "Aisha Patel",
  "email": "aisha@example.com",
  "role": "Software Engineer",
  "department": "Engineering",
  "cognito_role": "employee | manager | hr_admin",
  "manager_id": "mgr-001"
}
```

---

## Table: form_config

**Access patterns:**
- Get form by type → PK lookup on `form_type`

```json
{
  "form_type": "self | manager | peer",
  "title": "Self Review",
  "description": "...",
  "questions": [
    {
      "id": "q1",
      "text": "What were your top achievements?",
      "type": "text | rating",
      "min": 1,
      "max": 5
    }
  ]
}
```

---

## Table: review_submissions

**Access patterns:**
- Get all reviews for an employee in a cycle → GSI on `cycle_id` + `reviewee_id`
- Get a specific submission → PK lookup on `submission_id`

```json
{
  "submission_id": "uuid-string",
  "cycle_id": "uuid-string",
  "reviewee_id": "emp-001",
  "reviewer_id": "emp-002 (self/manager) | sha256-hash (peer)",
  "review_type": "self | manager | peer",
  "is_anonymous": false,
  "responses": [
    { "question_id": "q1", "type": "text", "value": "Shipped auth module" },
    { "question_id": "q3", "type": "rating", "value": 4 }
  ],
  "composite_score": 4.0,
  "submitted_at": "2025-10-15T09:42:00Z"
}
```

**Note:** For peer reviews, `reviewer_id` is `SHA256(raw_id:cycle_id:SALT)`.
The raw reviewer identity is never stored. See `docs/anonymisation.md`.

---

## Table: okr_tracker

**Access patterns:**
- Get OKRs for employee in a quarter → GSI on `employee_id` + `quarter`
- Update a specific OKR → PK lookup on `okr_id`

```json
{
  "okr_id": "uuid-string",
  "employee_id": "emp-001",
  "objective_title": "Ship new authentication module",
  "quarter": "2025-Q4",
  "key_results": [
    {
      "kr_id": "kr-a1",
      "title": "Complete OAuth 2.0 integration",
      "target_metric": "100% done",
      "progress": 80,
      "progress_history": [
        { "progress": 40, "notes": "In progress", "recorded_at": "2025-10-07T..." },
        { "progress": 80, "notes": "Almost done", "recorded_at": "2025-10-14T..." }
      ],
      "notes": ""
    }
  ],
  "overall_completion": 63.3,
  "created_at": "2025-10-01T...",
  "updated_at": "2025-10-14T..."
}
```

---

## Design Decisions

**Why no Sort Key on most tables?**
Single-entity lookups dominate (fetch one cycle, one submission). GSIs handle
the multi-value access patterns cleanly. Adding a sort key to the base table
would complicate writes without improving read performance for these patterns.

**Why `employee_ids` as a List in review_cycles?**
Cycles rarely have more than 200 employees — well within DynamoDB's 400KB item limit.
This avoids a separate cycle-employee mapping table and simplifies participant lookup.

**Why submission_id as PK instead of cycle_id + reviewer_id?**
A reviewer can submit multiple peer reviews in one cycle (for different reviewees).
Using a UUID PK avoids composite key collisions and keeps the schema flexible.
