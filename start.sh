#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# 360° Performance Review & OKR Tracking System — Startup Script
# Run this after cloning the repo to set up and launch the project
# Usage: chmod +x start.sh && ./start.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e  # Exit on any error

REGION="ap-south-1"
ENV="dev"
STACK_NAME="performance-review-system"
SES_EMAIL="oggyk81054@gmail.com"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   360° Performance Review & OKR Tracking System      ║${NC}"
echo -e "${BLUE}║   Startup Script                                      ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── STEP 1: Check prerequisites ───────────────────────────────────────────
echo -e "${BLUE}[1/6] Checking prerequisites...${NC}"

check_cmd() {
  if ! command -v $1 &> /dev/null; then
    echo -e "${RED}✗ $1 not found. Please install it and re-run.${NC}"
    exit 1
  else
    echo -e "${GREEN}✓ $1 found${NC}"
  fi
}

check_cmd aws
check_cmd sam
check_cmd python3
check_cmd node
check_cmd npm

echo ""

# ── STEP 2: Verify SES email ──────────────────────────────────────────────
echo -e "${BLUE}[2/6] Verifying SES sender email...${NC}"
STATUS=$(aws sesv2 list-email-identities --region $REGION \
  --query "EmailIdentities[?IdentityName=='$SES_EMAIL'].VerificationStatus" \
  --output text 2>/dev/null || echo "")

if [ "$STATUS" == "SUCCESS" ]; then
  echo -e "${GREEN}✓ $SES_EMAIL already verified in SES${NC}"
else
  echo -e "${YELLOW}→ Sending verification email to $SES_EMAIL...${NC}"
  aws ses verify-email-identity --email-address $SES_EMAIL --region $REGION
  echo -e "${YELLOW}⚠ Check your inbox and click the AWS verification link, then re-run this script.${NC}"
  exit 0
fi
echo ""

# ── STEP 3: Deploy infrastructure ────────────────────────────────────────
echo -e "${BLUE}[3/6] Building and deploying AWS infrastructure...${NC}"

# Check if stack already exists
STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --region $REGION --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$STACK_STATUS" == "CREATE_COMPLETE" ] || [ "$STACK_STATUS" == "UPDATE_COMPLETE" ]; then
  echo -e "${GREEN}✓ Stack already deployed (status: $STACK_STATUS)${NC}"
else
  echo -e "${YELLOW}→ Stack not found. Running sam deploy --guided...${NC}"
  echo -e "${YELLOW}  When prompted:${NC}"
  echo -e "${YELLOW}  • Stack name: $STACK_NAME${NC}"
  echo -e "${YELLOW}  • Region: $REGION${NC}"
  echo -e "${YELLOW}  • SESSourceEmail: $SES_EMAIL${NC}"
  echo -e "${YELLOW}  • PeerHashSalt: run 'openssl rand -hex 32' and paste${NC}"
  echo -e "${YELLOW}  • Environment: $ENV${NC}"
  echo -e "${YELLOW}  • Answer Y to all other prompts${NC}"
  echo ""
  cd infrastructure
  sam build
  sam deploy --guided
  cd ..
fi
echo ""

# ── STEP 4: Get stack outputs ─────────────────────────────────────────────
echo -e "${BLUE}[4/6] Fetching stack outputs...${NC}"

API_ENDPOINT=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --region $REGION --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
  --output text)

USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --region $REGION --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text)

CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME \
  --region $REGION --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
  --output text)

echo -e "${GREEN}✓ ApiEndpoint:      $API_ENDPOINT${NC}"
echo -e "${GREEN}✓ UserPoolId:       $USER_POOL_ID${NC}"
echo -e "${GREEN}✓ UserPoolClientId: $CLIENT_ID${NC}"
echo ""

# ── STEP 5: Write frontend .env ───────────────────────────────────────────
echo -e "${BLUE}[5/6] Configuring frontend .env...${NC}"
cat > frontend/.env << ENVEOF
VITE_API_BASE=$API_ENDPOINT
VITE_COGNITO_POOL_ID=$USER_POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
ENVEOF
echo -e "${GREEN}✓ frontend/.env written${NC}"
echo ""

# ── STEP 6: Seed database ─────────────────────────────────────────────────
echo -e "${BLUE}[6/6] Seeding database and creating Cognito users...${NC}"
cd seed-data
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install boto3 -q
python3 seed.py --env $ENV --region $REGION
deactivate
cd ..
echo ""

# ── DONE — Launch frontend ────────────────────────────────────────────────
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ✓ Setup complete! Launching the app...             ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Login credentials:${NC}"
echo -e "  HR Admin  → oggyk81054@gmail.com   / TempPass1!"
echo -e "  Manager   → davidjohncena12@gmail.com / TempPass1!"
echo -e "  Employee  → adilk3682@gmail.com    / TempPass1!"
echo -e "  Employee  → adilk81054@gmail.com   / TempPass1!"
echo -e "  Employee  → tariyonlannister3682@gmail.com / TempPass1!"
echo ""
echo -e "${BLUE}Opening http://localhost:3000${NC}"
echo ""

cd frontend
npm install -q
npm run dev
