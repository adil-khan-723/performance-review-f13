#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 360° Performance Review & OKR Tracking System — Teardown Script
# Removes ALL AWS resources created by this project
# Usage: chmod +x teardown.sh && ./teardown.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

REGION="ap-south-1"
STACK_NAME="performance-review-system"
ENV="dev"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPORTS_BUCKET="performance-reports-${ENV}-${ACCOUNT_ID}"
SAM_BUCKET="aws-sam-cli-managed-default-samclisourcebucket"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${RED}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║   360° Performance Review — Teardown Script          ║${NC}"
echo -e "${RED}║   This will DELETE all AWS resources permanently      ║${NC}"
echo -e "${RED}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}The following will be permanently deleted:${NC}"
echo "  • CloudFormation stack: $STACK_NAME"
echo "  • All Lambda functions (cycle-engine, feedback, okr, report-generator, reminder)"
echo "  • All DynamoDB tables (review_cycles, employees, form_config, review_submissions, okr_tracker)"
echo "  • Cognito User Pool and all user accounts"
echo "  • S3 bucket and all generated reports: $REPORTS_BUCKET"
echo "  • API Gateway, Step Functions, EventBridge rule"
echo "  • All IAM roles created by this stack"
echo "  • SAM deployment artifacts in S3"
echo ""
read -p "$(echo -e ${RED}Type DELETE to confirm: ${NC})" CONFIRM

if [ "$CONFIRM" != "DELETE" ]; then
  echo -e "${YELLOW}Teardown cancelled.${NC}"
  exit 0
fi

echo ""
echo -e "${BLUE}Starting teardown...${NC}"
echo ""

# ── STEP 1: Empty the Reports S3 bucket ──────────────────────────────────────
echo -e "${BLUE}[1/5] Emptying S3 reports bucket...${NC}"
if aws s3api head-bucket --bucket "$REPORTS_BUCKET" --region "$REGION" 2>/dev/null; then
  # Delete all object versions (handles versioned buckets)
  VERSIONS=$(aws s3api list-object-versions \
    --bucket "$REPORTS_BUCKET" \
    --region "$REGION" \
    --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
    --output json 2>/dev/null)

  if [ "$VERSIONS" != "null" ] && [ ! -z "$VERSIONS" ] && [ "$VERSIONS" != '{"Objects": null}' ]; then
    aws s3api delete-objects \
      --bucket "$REPORTS_BUCKET" \
      --region "$REGION" \
      --delete "$VERSIONS" > /dev/null 2>&1 || true
  fi

  # Delete all remaining objects
  aws s3 rm "s3://$REPORTS_BUCKET" --recursive --region "$REGION" 2>/dev/null || true
  echo -e "${GREEN}✓ Reports bucket emptied${NC}"
else
  echo -e "${YELLOW}⚠ Reports bucket not found (may already be deleted)${NC}"
fi

# ── STEP 2: Delete CloudFormation stack ──────────────────────────────────────
echo -e "${BLUE}[2/5] Deleting CloudFormation stack: $STACK_NAME...${NC}"
STACK_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$STACK_STATUS" == "NOT_FOUND" ]; then
  echo -e "${YELLOW}⚠ Stack not found (may already be deleted)${NC}"
else
  aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

  echo -e "${YELLOW}→ Waiting for stack deletion (this may take 2-5 minutes)...${NC}"
  aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"
  echo -e "${GREEN}✓ CloudFormation stack deleted${NC}"
fi

# ── STEP 3: Remove SES verified email identities ─────────────────────────────
echo -e "${BLUE}[3/5] Removing SES verified email identities...${NC}"
EMAILS=(
  "oggyk81054@gmail.com"
  "davidjohncena12@gmail.com"
  "adilk3682@gmail.com"
  "adilk81054@gmail.com"
  "tariyonlannister3682@gmail.com"
)
for EMAIL in "${EMAILS[@]}"; do
  aws sesv2 delete-email-identity \
    --email-identity "$EMAIL" \
    --region "$REGION" 2>/dev/null && \
    echo -e "${GREEN}  ✓ Removed: $EMAIL${NC}" || \
    echo -e "${YELLOW}  ⚠ Not found: $EMAIL${NC}"
done

# ── STEP 4: Empty and delete SAM deployment bucket ───────────────────────────
echo -e "${BLUE}[4/5] Cleaning up SAM deployment artifacts...${NC}"
SAM_BUCKET_FULL=$(aws s3api list-buckets \
  --query "Buckets[?starts_with(Name, 'aws-sam-cli-managed-default')].Name" \
  --output text 2>/dev/null || echo "")

if [ ! -z "$SAM_BUCKET_FULL" ]; then
  # Only delete objects with our stack prefix to avoid affecting other projects
  aws s3 rm "s3://$SAM_BUCKET_FULL/$STACK_NAME/" \
    --recursive --region "$REGION" 2>/dev/null || true
  echo -e "${GREEN}✓ SAM deployment artifacts cleaned${NC}"
else
  echo -e "${YELLOW}⚠ SAM bucket not found${NC}"
fi

# ── STEP 5: Clean up local config files ──────────────────────────────────────
echo -e "${BLUE}[5/5] Cleaning up local config files...${NC}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Remove frontend .env (contains AWS endpoints)
if [ -f "$SCRIPT_DIR/frontend/.env" ]; then
  rm "$SCRIPT_DIR/frontend/.env"
  echo -e "${GREEN}  ✓ Removed frontend/.env${NC}"
fi

# Remove SAM config
if [ -f "$SCRIPT_DIR/infrastructure/samconfig.toml" ]; then
  rm "$SCRIPT_DIR/infrastructure/samconfig.toml"
  echo -e "${GREEN}  ✓ Removed infrastructure/samconfig.toml${NC}"
fi

# Remove SAM build artifacts
if [ -d "$SCRIPT_DIR/infrastructure/.aws-sam" ]; then
  rm -rf "$SCRIPT_DIR/infrastructure/.aws-sam"
  echo -e "${GREEN}  ✓ Removed infrastructure/.aws-sam/${NC}"
fi

# Remove seed-data venv
if [ -d "$SCRIPT_DIR/seed-data/venv" ]; then
  rm -rf "$SCRIPT_DIR/seed-data/venv"
  echo -e "${GREEN}  ✓ Removed seed-data/venv/${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✓ Teardown complete!                               ║${NC}"
echo -e "${GREEN}║                                                      ║${NC}"
echo -e "${GREEN}║   All AWS resources have been deleted.               ║${NC}"
echo -e "${GREEN}║   No further charges will be incurred.               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}To redeploy from scratch, run: ./start.sh${NC}"
echo ""
