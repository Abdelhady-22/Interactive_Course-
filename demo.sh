#!/bin/bash
# ============================================================
# Interactive Course Platform — Demo Script
# Runs the full pipeline and shows clean results
# ============================================================

set -e

API="http://localhost:8000"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
YELLOW="\033[33m"
RESET="\033[0m"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Interactive Course Platform — AI Layout Director      ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${RESET}"
echo ""

# --- Step 1: Health Check ---
echo -e "${CYAN}[1/7] Checking system health...${RESET}"
HEALTH=$(curl -sf "$API/health/detailed" 2>/dev/null || echo '{"status":"unreachable"}')
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
echo ""

# --- Step 2: Get Course ---
echo -e "${CYAN}[2/7] Finding course...${RESET}"
COURSES=$(curl -sf "$API/api/courses/")
COURSE_ID=$(echo "$COURSES" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['courses'][0]['id'])" 2>/dev/null)

if [ -z "$COURSE_ID" ]; then
    echo "ERROR: No courses found. Run migrations first."
    exit 1
fi

COURSE_TITLE=$(echo "$COURSES" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['courses'][0]['title'])" 2>/dev/null)
PARA_COUNT=$(echo "$COURSES" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['courses'][0]['paragraph_count'])" 2>/dev/null)
ASSET_COUNT=$(echo "$COURSES" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['courses'][0]['asset_count'])" 2>/dev/null)

echo -e "  Course:     ${GREEN}$COURSE_TITLE${RESET}"
echo -e "  ID:         $COURSE_ID"
echo -e "  Paragraphs: $PARA_COUNT"
echo -e "  Assets:     $ASSET_COUNT"
echo ""

# --- Step 3: Process Course ---
echo -e "${CYAN}[3/7] Running AI agent on all paragraphs...${RESET}"
echo -e "${YELLOW}  (This may take 30-90 seconds with Groq API)${RESET}"
echo ""

RESULT=$(curl -sf -X POST "$API/api/courses/$COURSE_ID/process")
TOTAL=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])" 2>/dev/null)
echo -e "  [OK] Processed ${GREEN}$TOTAL paragraphs${RESET}"
echo ""

# --- Step 4: Show Decisions Summary ---
echo -e "${CYAN}[4/7] Decision Summary:${RESET}"
echo ""
echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  {'#':<4} {'Layout Mode':<25} {'Decided By':<16} {'Confidence':<12} Pinned')
print(f'  {'-'*4} {'-'*25} {'-'*16} {'-'*12} {'-'*6}')
for i, d in enumerate(data['decisions'], 1):
    mode = d['layout']['mode']
    by = d['decided_by']
    conf = f\"{d['confidence']:.0%}\"
    pinned = 'YES' if d.get('continuity', {}).get('pin_instructor') else '   '
    print(f'  {i:<4} {mode:<25} {by:<16} {conf:<12} {pinned}')
print()
print(f'  Total: {data[\"total\"]} decisions, {data[\"approved_count\"]} pre-approved')
"
echo ""

# --- Step 5: Show One Full Decision ---
echo -e "${CYAN}[5/7] Sample Decision (Paragraph 1):${RESET}"
echo ""
echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
d = data['decisions'][0]
print(json.dumps(d, indent=2))
" 2>/dev/null
echo ""

# --- Step 6: Approve & Publish ---
echo -e "${CYAN}[6/7] Approving all decisions and publishing...${RESET}"
curl -sf -X POST "$API/api/courses/$COURSE_ID/approve-all" > /dev/null
PUBLISH=$(curl -sf -X POST "$API/api/courses/$COURSE_ID/publish")
echo "$PUBLISH" | python3 -m json.tool 2>/dev/null
echo ""

# --- Step 7: Save Playback JSON ---
echo -e "${CYAN}[7/7] Saving playback JSON to output.json...${RESET}"
curl -sf "$API/api/courses/$COURSE_ID/playback" | python3 -m json.tool > output.json
FILESIZE=$(wc -c < output.json)
echo -e "  [OK] Saved to ${GREEN}output.json${RESET} (${FILESIZE} bytes)"
echo ""

echo -e "${BOLD}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   Demo Complete!                                        ║${RESET}"
echo -e "${BOLD}║                                                          ║${RESET}"
echo -e "${BOLD}║   output.json — Full playback data                      ║${RESET}"
echo -e "${BOLD}║   http://localhost:8000/docs — Swagger UI                ║${RESET}"
echo -e "${BOLD}║   http://localhost:8000/health/detailed — Status         ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════╝${RESET}"
echo ""
