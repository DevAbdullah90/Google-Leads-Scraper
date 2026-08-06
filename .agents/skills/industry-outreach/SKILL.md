# Industry Outreach

Personalized cold email outreach for **healthcare**, **education**, and **real estate** businesses. Mines scraped Google reviews for pain-point hooks to craft relevant, high-converting emails. Includes automated follow-up system.

## When To Use

Use this skill when:
- Sending outreach emails to leads scraped from Google Maps
- Targeting healthcare clinics/practices, education institutions/tutoring centers, or real estate agencies
- You want to personalize emails based on actual customer review pain points
- User asks to "send outreach emails" or "email leads" or "start outreach campaign"
- User asks to "send follow-up emails" or "follow up on previous outreach"

## Input Requirements

The user must provide:
1. **Industry**: One of `healthcare`, `education`, or `real estate`
2. **Google Sheet ID** (or use default from `.env`)
3. **Sheet name**: Which tab contains the leads

## Two Workflows

### Workflow A: Initial Outreach (New Leads)
Reads from **Scraped Leads** tab → sends personalized email → logs to **Follow Up** tab

### Workflow B: Follow-Up (Existing Leads)
Reads from **Follow Up** tab → sends follow-up email → updates row in **Follow Up** tab

---

## Workflow A: Initial Outreach

### Step 1: Read Leads from Google Sheet

```
google-sheets_read-range
  spreadsheet_id: (from user or .env GOOGLE_SHEETS_SPREADSHEET_ID)
  range_name: "{Sheet Name}!A1:AA"
```

Expected columns (A–AA):
- A: Place ID
- B: Name
- C: Phone
- D: Website
- E: Rating
- F: Total Reviews
- G: Address
- H: Business Status
- I: Category
- J: Scraped Date
- K: Scraped Time
- L: Additional Phones
- M: Email
- N: Owner Name
- O: Owner Title
- P: LinkedIn
- Q: Facebook
- R: Instagram
- S: Google Ads Running
- T: Google Ads Count
- U: Description
- V: All Categories
- W: Price Level
- X: Years in Business
- Y: Social Links (all)
- Z: Attributes
- AA: Reviews Sample ← **key field for pain-point mining**

### Step 2: Filter & Prioritize Leads

Filter out leads that:
- Have no email address (col M is empty)
- Have `Business Status` = "CLOSED_TEMPORARILY" or "CLOSED_PERMANENTLY"

Prioritize leads with:
- More reviews (higher col F) — more pain-point data available
- Higher ratings (col E ≥ 4.0) — established businesses, more likely to invest

### Step 3: Mine Reviews for Pain-Point Hooks

Read **col AA (Reviews Sample)** for each lead. Analyze review text for industry-specific pain points using the mapping below.

#### Healthcare Pain Points

| Pain Point Pattern | Keywords in Reviews | Hook Angle |
|---|---|---|
| Long wait times | "wait", "waiting", "hours", "long time", "delayed" | Automate appointment booking to reduce phone hold times |
| Missed calls | "couldn't reach", "no answer", "busy", "called back" | 24/7 AI receptionist never misses a call |
| Scheduling difficulties | "appointment", "book", "schedule", "hard to book" | Instant online booking without phone tag |
| Staff overwhelmed | "rushed", "overwhelmed", "short staff", "busy" | Reduce front desk burden with AI triage |
| Patient no-shows | "forgot", "missed appointment", "no show" | Automated reminders via WhatsApp/SMS |
| Billing confusion | "bill", "confused", "insurance", "unclear" | AI assistant answers billing FAQs instantly |

#### Education Pain Points

| Pain Point Pattern | Keywords in Reviews | Hook Angle |
|---|---|---|
| Slow inquiry response | "slow reply", "no response", "waiting for reply", "took days" | Instant AI response to parent/student inquiries |
| Enrollment friction | "enrollment", "enroll", "sign up", "registration" | Streamline enrollment with AI-guided process |
| Communication gaps | "no communication", "didn't inform", "unclear", "confused" | Automated updates on student progress |
| Availability issues | "fully booked", "no availability", "waitlist", "full" | AI manages waitlists and notifies on openings |
| Pricing transparency | "pricing", "cost", "expensive", "unclear fees" | AI answers pricing questions instantly |
| Admin overhead | "paperwork", "forms", "manual", "admin" | Automate admissions paperwork with AI |

#### Real Estate Pain Points

| Pain Point Pattern | Keywords in Reviews | Hook Angle |
|---|---|---|
| Slow response to inquiries | "slow reply", "no response", "never called back", "ignored" | 24/7 AI instantly responds to property inquiries |
| Missed WhatsApp leads | "whatsapp", "message", "no reply", "seen but not replied" | AI auto-replies to every WhatsApp inquiry |
| Property info delays | "property details", "floor plan", "pricing", "no info" | Instant property info sharing via AI |
| Viewing scheduling issues | "viewing", "schedule", "tour", "hard to book" | AI books viewings automatically |
| After-hours inquiries | "after hours", "weekend", "late", "night" | Never miss a lead — AI works 24/7 |
| Follow-up failures | "follow up", "never followed up", "forgot about me" | Automated follow-up sequences |

### Step 4: Generate Personalized Emails

For each lead, compose a personalized email using the industry-specific template.

**Personalization tokens** (replace in templates):
- `{business_name}` — exact name from col B
- `{rating}` — from col E
- `{review_count}` — from col F
- `{location}` — from col G (extract city/area)
- `{category}` — from col I
- `{pain_hook}` — specific pain point mined from reviews (col AA)
- `{email}` — recipient from col M
- `{signature}` — HTML signature from `config/email_signature.html`

**Pain-hook rules:**
- If review text contains a clear pain point, use it as the opening hook
- If no pain point found, fall back to a generic hook (rating, review count, or location)
- Never fabricate pain points — only reference what's actually in the reviews
- Keep hooks specific: "I noticed a reviewer mentioned waiting 45 minutes for a callback" not "some people complain"

### Step 5: Send via Zoho Mail MCP

Use `ZohoMCP_ZohoMail_sendEmail` to send each email.

**Required parameters:**
- `accountId`: `6031472000000008002`
- `fromAddress`: `info@nexeagent.com`
- `toAddress`: lead's email (col M)
- `subject`: personalized subject line
- `content`: full HTML email wrapped in `<html><body>` tags
- `mailFormat`: `html`

**IMPORTANT email formatting rules:**
1. Wrap ALL content in `<html><body>` tags
2. Use `<br>` for line breaks, NOT `\n`
3. Use `<p>` tags for paragraphs
4. ALWAYS embed the HTML signature directly — `includeSignature: true` does NOT work
5. Read signature from `config/email_signature.html` and append to email content

### Step 6: Log to Follow Up Tab

After each email is sent, append the lead to the **Follow Up** tab:

```
google-sheets_append-rows
  spreadsheet_id: (same sheet)
  range_name: "Follow Up!A:F"
  values: [[business_name, email, industry, pain_hook_used, sent_date, 0]]
```

If the "Follow Up" tab doesn't exist, create it first with headers:
`Business Name | Email | Industry | Pain Hook | Sent Date | Follow-up Count`

The `Follow-up Count` starts at `0` (initial email sent).

---

## Workflow B: Follow-Up Emails

### Step 1: Read Follow Up Tab

```
google-sheets_read-range
  spreadsheet_id: (from user or .env GOOGLE_SHEETS_SPREADSHEET_ID)
  range_name: "Follow Up!A1:F"
```

**Follow Up Tab Structure:**

| A | B | C | D | E | F |
|---|---|---|---|---|---|
| Business Name | Email | Industry | Pain Hook | Sent Date | Follow-up Count |

### Step 2: Filter Leads for Follow-Up

Filter leads where:
- `Follow-up Count` (col F) is less than 3
- `Sent Date` (col E) was 3+ days ago

Calculate days since `Sent Date`:
- **Follow-up #1**: 3–6 days since last email, `Follow-up Count` = 0
- **Follow-up #2**: 7–13 days since last email, `Follow-up Count` = 1
- **Follow-up #3**: 14+ days since last email, `Follow-up Count` = 2

### Step 3: Generate Follow-Up Email

Compose a follow-up email using the appropriate template based on `Follow-up Count`.

**Follow-up email rules:**
- Reference the original pain hook from col D
- Reference the original email timing: "In my last email from {sent_date}..."
- Escalate urgency with each follow-up
- Keep tone professional, not pushy
- Use the same industry-specific template set (see `references/email_templates.md`)

**Personalization tokens for follow-ups:**
- `{business_name}` — from col A
- `{email}` — from col B
- `{industry}` — from col C
- `{original_pain_hook}` — from col D
- `{last_sent_date}` — from col E
- `{follow_up_number}` — from col F + 1 (1, 2, or 3)
- `{signature}` — HTML signature from `config/email_signature.html`

### Step 4: Send Follow-Up via Zoho Mail MCP

Use `ZohoMCP_ZohoMail_sendEmail` with the same parameters as initial outreach.

### Step 5: Update Follow Up Tab

After sending follow-up, update the row:

**If Follow-up Count is currently 0 → becomes 1:**
```
google-sheets_write-range
  spreadsheet_id: (same sheet)
  range_name: "Follow Up!F{row_number}"
  values: [[1]]
```

**If Follow-up Count is currently 1 → becomes 2:**
```
google-sheets_write-range
  spreadsheet_id: (same sheet)
  range_name: "Follow Up!F{row_number}"
  values: [[2]]
```

**If Follow-up Count is currently 2 → becomes 3:**
```
google-sheets_write-range
  spreadsheet_id: (same sheet)
  range_name: "Follow Up!F{row_number}"
  values: [[3]]
```

**Follow-up Count = 3 means no more follow-ups.**

---

## Follow-Up Email Templates

See `references/email_templates.md` for full templates including follow-up sequences.

### Follow-Up #1 (Day 3) — Gentle Reminder

**Healthcare:**
```
Subject: Quick follow-up — {business_name} patient scheduling
```

**Education:**
```
Subject: Following up — {business_name} enrollment inquiries
```

**Real Estate:**
```
Subject: Quick follow-up — {business_name} WhatsApp leads
```

### Follow-Up #2 (Day 7) — Different Angle + Urgency

**Healthcare:**
```
Subject: {business_name} — patients are calling, are you answering?
```

**Education:**
```
Subject: {business_name} — competitors are responding faster
```

**Real Estate:**
```
Subject: {business_name} — every missed WhatsApp = lost commission
```

### Follow-Up #3 (Day 14) — Final Attempt

**Healthcare:**
```
Subject: Last note — {business_name} patient booking
```

**Education:**
```
Subject: Final follow-up — {business_name} enrollment
```

**Real Estate:**
```
Subject: Closing the loop — {business_name} property inquiries
```

---

## Email Templates

See `references/email_templates.md` for full templates per industry (initial + all 3 follow-ups).

### Quick Subject Line Patterns (Initial Outreach)

**Healthcare:**
- "Help {business_name} patients book appointments without the hold music"
- "{business_name} — your {review_count} patients deserve faster scheduling"

**Education:**
- "{business_name} — never miss a parent inquiry again"
- "With {review_count} reviews, {business_name} needs instant enrollment responses"

**Real Estate:**
- "{business_name} — capture every WhatsApp lead 24/7"
- "{business_name}'s {rating} rating deserves 24/7 WhatsApp support"

## What NOT to Say

- "AI-powered" → use "smart assistant" or "automated"
- "LLM" or "large language model"
- "API integration"
- "Machine learning"
- "Chatbot" → use "assistant" or "helper"
- "Automation workflow"
- "Technical implementation"

## What TO Say

- "Instantly replies"
- "24/7 support"
- "Never miss a lead"
- "Faster response times"
- "More qualified leads"
- "Better customer experience"
- "Without hiring additional staff"
- "Automatically handles"
- "Smart assistant"

## Execution Commands

### Initial Outreach

```
User: "Send outreach emails to healthcare leads from Scraped Leads tab"
Agent:
1. Read Scraped Leads tab (cols A–AA)
2. Filter leads with valid emails
3. Mine reviews for pain points (col AA)
4. Generate personalized emails
5. Send via Zoho Mail MCP
6. Log each sent email to Follow Up tab (cols A–F, count = 0)
```

### Follow-Up Campaign

```
User: "Send follow-up emails"
Agent:
1. Read Follow Up tab (cols A–F)
2. Filter where Follow-up Count < 3 AND Sent Date is 3+ days ago
3. Generate follow-up emails (reference original pain hook + timing)
4. Send via Zoho Mail MCP
5. Update Follow-up Count in Follow Up tab (increment by 1)
```

## Notes

- Always confirm with user before sending (show 3 sample emails first)
- Rate limit: max 10 emails per batch, wait 5 seconds between sends
- If an email fails, log it and continue with the next lead
- Never send to leads without a valid email address
- Every email sent goes to Follow Up tab — no exceptions
- Follow-up Count starts at 0, maxes at 3
- No reply tracking needed — all leads stay in Follow Up tab regardless of replies
