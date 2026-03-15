#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 360° Performance Review & OKR Tracking System — Full Setup Script
# Provisions entire AWS infrastructure and launches the application
# Usage: chmod +x start.sh && ./start.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

REGION="ap-south-1"
ENV="dev"
STACK_NAME="performance-review-system"
SES_EMAIL="oggyk81054@gmail.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   360° Performance Review & OKR Tracking System      ║${NC}"
echo -e "${BLUE}║   Full Setup & Launch Script                         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── STEP 1: Check prerequisites ───────────────────────────────────────────────
echo -e "${BLUE}[1/7] Checking prerequisites...${NC}"

MISSING=0
check_cmd() {
  if ! command -v $1 &> /dev/null; then
    echo -e "${RED}  ✗ $1 not found${NC}"
    MISSING=1
  else
    VERSION=$($1 --version 2>&1 | head -1)
    echo -e "${GREEN}  ✓ $1${NC} — $VERSION"
  fi
}

check_cmd aws
check_cmd sam
check_cmd python3
check_cmd node
check_cmd npm

if [ $MISSING -eq 1 ]; then
  echo ""
  echo -e "${RED}Some prerequisites are missing. Install them and re-run.${NC}"
  echo -e "${YELLOW}  AWS CLI:  brew install awscli && aws configure${NC}"
  echo -e "${YELLOW}  SAM CLI:  brew install aws-sam-cli${NC}"
  echo -e "${YELLOW}  Python:   brew install python@3.11${NC}"
  echo -e "${YELLOW}  Node.js:  brew install node${NC}"
  exit 1
fi

# Check AWS credentials
echo -e "${BLUE}  Checking AWS credentials...${NC}"
IDENTITY=$(aws sts get-caller-identity --output json 2>/dev/null || echo "")
if [ -z "$IDENTITY" ]; then
  echo -e "${RED}  ✗ AWS credentials not configured. Run: aws configure${NC}"
  exit 1
fi
ACCOUNT_ID=$(echo $IDENTITY | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])")
AWS_USER=$(echo $IDENTITY | python3 -c "import sys,json; print(json.load(sys.stdin)['Arn'])")
echo -e "${GREEN}  ✓ AWS credentials valid${NC} — $AWS_USER"
echo ""

# ── STEP 2: Verify SES email ──────────────────────────────────────────────────
echo -e "${BLUE}[2/7] Checking SES email verification...${NC}"

SES_STATUS=$(aws sesv2 list-email-identities --region $REGION \
  --query "EmailIdentities[?IdentityName=='$SES_EMAIL'].VerificationStatus" \
  --output text 2>/dev/null || echo "")

if [ "$SES_STATUS" == "SUCCESS" ]; then
  echo -e "${GREEN}  ✓ $SES_EMAIL is verified in SES${NC}"
else
  echo -e "${YELLOW}  → Sending verification email to $SES_EMAIL...${NC}"
  aws ses verify-email-identity --email-address $SES_EMAIL --region $REGION
  echo ""
  echo -e "${YELLOW}  ⚠ ACTION REQUIRED:${NC}"
  echo -e "${YELLOW}    Check the inbox of $SES_EMAIL${NC}"
  echo -e "${YELLOW}    Click the AWS verification link in the email${NC}"
  echo -e "${YELLOW}    Then re-run this script: ./start.sh${NC}"
  exit 0
fi

# Verify all employee emails
echo -e "${BLUE}  Checking employee email verifications...${NC}"
EMPLOYEE_EMAILS=(
  "davidjohncena12@gmail.com"
  "adilk3682@gmail.com"
  "adilk81054@gmail.com"
  "tariyonlannister3682@gmail.com"
)
UNVERIFIED=()
for EMAIL in "${EMPLOYEE_EMAILS[@]}"; do
  STATUS=$(aws sesv2 list-email-identities --region $REGION \
    --query "EmailIdentities[?IdentityName=='$EMAIL'].VerificationStatus" \
    --output text 2>/dev/null || echo "")
  if [ "$STATUS" == "SUCCESS" ]; then
    echo -e "${GREEN}    ✓ $EMAIL${NC}"
  else
    echo -e "${YELLOW}    → Sending verification to $EMAIL...${NC}"
    aws ses verify-email-identity --email-address $EMAIL --region $REGION 2>/dev/null || true
    UNVERIFIED+=("$EMAIL")
  fi
done

if [ ${#UNVERIFIED[@]} -gt 0 ]; then
  echo ""
  echo -e "${YELLOW}  ⚠ Verification emails sent to ${#UNVERIFIED[@]} address(es).${NC}"
  echo -e "${YELLOW}    Each person must click the verification link in their inbox.${NC}"
  echo -e "${YELLOW}    Notifications will only land after verification.${NC}"
  echo -e "${YELLOW}    Continuing setup — you can verify emails while setup runs.${NC}"
fi
echo ""

# ── STEP 3: Deploy infrastructure ────────────────────────────────────────────
echo -e "${BLUE}[3/7] Deploying AWS infrastructure...${NC}"

STACK_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].StackStatus" \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$STACK_STATUS" == "CREATE_COMPLETE" ] || [ "$STACK_STATUS" == "UPDATE_COMPLETE" ]; then
  echo -e "${GREEN}  ✓ Stack already deployed (status: $STACK_STATUS)${NC}"
  echo -e "${YELLOW}  → Skipping deploy. To redeploy, run: sam build && sam deploy${NC}"
else
  echo -e "${YELLOW}  → Stack not found. Starting full deployment...${NC}"
  echo ""

  # Generate PeerHashSalt
  SALT=$(openssl rand -hex 32)
  echo -e "${YELLOW}  ╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${YELLOW}  ║  IMPORTANT: Save your PeerHashSalt                  ║${NC}"
  echo -e "${YELLOW}  ║  $SALT  ║${NC}"
  echo -e "${YELLOW}  ║  Store this securely — you will need it to redeploy  ║${NC}"
  echo -e "${YELLOW}  ╚══════════════════════════════════════════════════════╝${NC}"
  echo ""

  # Save salt to a local file for reference
  echo "$SALT" > "$SCRIPT_DIR/.peer_hash_salt"
  echo -e "${GREEN}  ✓ Salt saved to .peer_hash_salt (add this to .gitignore!)${NC}"
  echo ""

  # Build
  echo -e "${BLUE}  Building Lambda packages...${NC}"
  cd "$SCRIPT_DIR/infrastructure"
  sam build
  echo -e "${GREEN}  ✓ Build complete${NC}"
  echo ""

  # Deploy
  echo -e "${BLUE}  Deploying to AWS (this takes ~5 minutes)...${NC}"
  sam deploy \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
      "SESSourceEmail=$SES_EMAIL" \
      "PeerHashSalt=$SALT" \
      "Environment=$ENV" \
    --no-confirm-changeset \
    --no-fail-on-empty-changeset \
    --resolve-s3

  cd "$SCRIPT_DIR"
  echo -e "${GREEN}  ✓ Deployment complete${NC}"
fi
echo ""

# ── STEP 4: Fetch stack outputs ───────────────────────────────────────────────
echo -e "${BLUE}[4/7] Fetching stack outputs...${NC}"

get_output() {
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" \
    --output text
}

API_ENDPOINT=$(get_output "ApiEndpoint")
USER_POOL_ID=$(get_output "UserPoolId")
CLIENT_ID=$(get_output "UserPoolClientId")
REPORTS_BUCKET=$(get_output "ReportsBucketName")
STATE_MACHINE=$(get_output "StateMachineArn")

echo -e "${GREEN}  ✓ ApiEndpoint:      ${NC}$API_ENDPOINT"
echo -e "${GREEN}  ✓ UserPoolId:       ${NC}$USER_POOL_ID"
echo -e "${GREEN}  ✓ UserPoolClientId: ${NC}$CLIENT_ID"
echo -e "${GREEN}  ✓ ReportsBucket:    ${NC}$REPORTS_BUCKET"
echo -e "${GREEN}  ✓ StateMachine:     ${NC}$STATE_MACHINE"
echo ""

# ── STEP 5: Write frontend .env ───────────────────────────────────────────────
echo -e "${BLUE}[5/7] Configuring frontend environment...${NC}"

cat > "$SCRIPT_DIR/frontend/.env" << ENVEOF
VITE_API_BASE=$API_ENDPOINT
VITE_COGNITO_POOL_ID=$USER_POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
ENVEOF

echo -e "${GREEN}  ✓ frontend/.env written${NC}"
echo ""

# ── STEP 6: Seed database and create Cognito users ────────────────────────────
echo -e "${BLUE}[6/7] Seeding database and creating user accounts...${NC}"

cd "$SCRIPT_DIR/seed-data"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo -e "${YELLOW}  → Creating Python virtual environment...${NC}"
  python3 -m venv venv
fi

source venv/bin/activate
pip install boto3 -q --upgrade

echo -e "${YELLOW}  → Running seed script...${NC}"
python3 seed.py --env "$ENV" --region "$REGION" --user-pool-id "$USER_POOL_ID"
deactivate

cd "$SCRIPT_DIR"
echo ""

# ── STEP 7: Install frontend deps and launch ──────────────────────────────────
echo -e "${BLUE}[7/7] Installing frontend dependencies and launching app...${NC}"
cd "$SCRIPT_DIR/frontend"

echo -e "${YELLOW}  → Running npm install...${NC}"
npm install --silent

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✓ Setup complete! Launching 360° Performance Review...        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}  App URL:${NC}    http://localhost:3000"
echo ""
echo -e "${BOLD}  Login Credentials (password: TempPass1!):${NC}"
echo -e "  ${BLUE}HR Admin${NC}   → oggyk81054@gmail.com"
echo -e "  ${BLUE}Manager${NC}    → davidjohncena12@gmail.com"
echo -e "  ${BLUE}Employee 1${NC} → adilk3682@gmail.com       (emp-001)"
echo -e "  ${BLUE}Employee 2${NC} → adilk81054@gmail.com      (emp-002)"
echo -e "  ${BLUE}Employee 3${NC} → tariyonlannister3682@gmail.com (emp-003)"
echo ""
echo -e "${YELLOW}  To tear down all AWS resources: ./teardown.sh${NC}"
echo ""

npm run dev
