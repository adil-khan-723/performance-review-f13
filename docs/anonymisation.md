# Peer Reviewer Anonymisation — Technical Explanation

## Overview

This system guarantees that peer reviewers cannot be identified from stored review data.
The mechanism uses **one-way SHA-256 hashing with a server-side salt**.

---

## How It Works

### 1. Submission flow

When an employee submits a peer review (`review_type = "peer"`), the Lambda function:

```
raw_reviewer_id = "emp-002"   ← from Cognito JWT (never stored)
cycle_id        = "abc-123"
SALT            = <secret value from environment variable>

hash_input = f"{raw_reviewer_id}:{cycle_id}:{SALT}"
stored_reviewer_id = SHA256(hash_input)
             = "7f83b1657ff1fc53b92dc18148a1d65..." (64 hex chars)
```

The `stored_reviewer_id` — the hash — is what gets written to DynamoDB.  
The `raw_reviewer_id` is **never written anywhere**.

### 2. What is stored in DynamoDB

```json
{
  "submission_id": "uuid",
  "cycle_id": "abc-123",
  "reviewee_id": "emp-001",
  "reviewer_id": "7f83b1657ff1fc53...",   ← hash only, not the real ID
  "review_type": "peer",
  "is_anonymous": true,
  "responses": [...],
  "composite_score": 4.2,
  "submitted_at": "2025-10-15T09:42:00Z"
}
```

### 3. For self and manager reviews

Self and manager reviews are **not anonymous** — the raw `reviewer_id` is stored.
This is intentional: managers must be accountable for their evaluations,
and self-reviews are inherently attributed.

---

## Why the Hash Cannot Be Reversed

### SHA-256 is a one-way function

Given `hash = SHA256(input)`, there is no algorithm to compute `input` from `hash`.
An attacker with the hash cannot learn the reviewer's employee ID without:

1. Knowing the exact SALT value (stored in environment variables, not in DynamoDB)
2. Having a list of all possible reviewer IDs
3. Computing `SHA256(candidate:cycle_id:SALT)` for every candidate until one matches

### The SALT prevents rainbow table attacks

Without a salt, an attacker could precompute `SHA256(emp-001)`, `SHA256(emp-002)`, etc.
The salt — unique to this deployment — means precomputed tables are useless.

### The cycle_id is part of the input

Including `cycle_id` means the same employee gets a different hash in every review cycle.
This prevents cross-cycle correlation of peer reviewer identities.

---

## What HR Admin Can (and Cannot) See

| Action | HR Admin | Manager | Employee |
|---|---|---|---|
| See peer review responses | ✓ | ✓ (own team) | ✓ (own reviews received) |
| See who wrote a specific peer review | ✗ | ✗ | ✗ |
| See aggregated peer score | ✓ | ✓ | ✓ |
| See raw `reviewer_id` for peer review | ✗ (hash only) | ✗ | ✗ |
| See raw `reviewer_id` for self/manager review | ✓ | ✓ | ✓ (own) |

---

## Production Hardening Recommendations

1. **Move SALT to AWS Secrets Manager** — do not store it in Lambda environment variables in production.
2. **Rotate the SALT between cycles** — reduces risk if the salt is ever compromised.
3. **Minimum peer reviewers per report** — require at least 3 peer reviews before displaying
   aggregated peer score, to prevent identity inference from a single-reviewer scenario.
4. **Audit log separation** — Lambda invocation logs (CloudWatch) may contain Cognito sub IDs.
   Ensure CloudWatch log access is restricted to security team only.

---

## Code Reference

The hashing logic lives in one place only:

```python
# backend/functions/feedback/handler.py — submit_review()

PEER_HASH_SALT = os.environ.get("PEER_HASH_SALT", "...")

if review_type == "peer":
    hash_input = f"{reviewer_id}:{cycle_id}:{PEER_HASH_SALT}"
    stored_reviewer_id = hashlib.sha256(hash_input.encode()).hexdigest()
    is_anonymous = True
```

The `reviewer_id` variable (raw Cognito employee ID) goes out of scope immediately after
this block and is **never passed to any DynamoDB write operation** for peer reviews.
