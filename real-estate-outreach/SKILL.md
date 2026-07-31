---
name: real-estate-outreach
description: Send personalized cold emails to real estate leads from Google Sheets. Use when the user says "email the leads", "send outreach", "process new leads", "email unsent leads", or any variation of sending emails to leads from the spreadsheet.
---

# Real Estate AI Outreach Automation

This skill automates sending personalized cold emails to real estate leads from Google Sheets.

## Quick Start

When the user says "email the leads" or similar:

1. Read the Google Sheet to find unsent leads
2. Generate personalized emails for each
3. Send via Zoho Mail MCP
4. Report summary at the end

## Configuration

- **Spreadsheet ID**: `1-pNAcHLkZtERS3KZqSt9l-wPb0QIXdXDgSdCtmSAnGk`
- **Sheet Name**: `Scraped Leads`
- **Account ID**: `6031472000000008002`
- **From Address**: `info@nexeagent.com`
- **Signature File**: `config/email_signature.html`

## Column Structure

| Column | Field |
|--------|-------|
| A | Business Name |
| B | Phone |
| C | Email |
| D | Website |
| E | Category |
| F | Rating |
| G | Reviews |
| H | Full Address |
| I | Google Maps URL |
| J | Status (SENT/FAILED/empty) |
| K | Sent Date |

## Workflow

### Step 1: Read Unsont Leads

```
Read range: Scraped Leads!A1:K1000
Filter: Column J (Status) is empty AND Column C (Email) is not empty
Limit: Process requested number (default: 10)
```

### Step 2: Generate Personalized Email

For each lead, create a unique email referencing:

- **Business name** in greeting
- **Google rating** ("I noticed your impressive 4.8 rating...")
- **Location** ("Operating in Abu Dhabi...")
- **Reviews count** ("With 380 reviews...")
- **Business category** ("As a leading real estate agency...")
- **Website** ("Your website shows...")

### Step 3: Email Format (HTML)

```html
<html>
<body>
<p>Dear [Contact Name],</p>
<p>[Personalized opening referencing their business]</p>
<p>[Pitch about AI WhatsApp Assistant - focus on business outcomes]</p>
<p>[Call to action for demo/discovery call]</p>
<p>Best regards,</p>
[SIGNATURE FROM config/email_signature.html]
</body>
</html>
```

### Step 4: Send via Zoho Mail MCP

```json
{
  "fromAddress": "info@nexeagent.com",
  "toAddress": "recipient@example.com",
  "subject": "Personalized Subject Line",
  "content": "<html>...</html>",
  "mailFormat": "html"
}
```

## Email Template Guidelines

### Subject Line Ideas
- "Help [Business Name] capture every WhatsApp lead 24/7"
- "Never miss a property inquiry again, [Business Name]"
- "[Business Name] - Automate your WhatsApp responses"
- "Quick question about your WhatsApp lead response time"

### Email Body Structure (150-220 words)

1. **Personalized greeting** - Use business name
2. **Observation** - Reference something specific (rating, reviews, location)
3. **Problem statement** - Missed WhatsApp inquiries after hours
4. **Solution pitch** - AI WhatsApp Assistant (business outcomes only)
5. **Benefits** - Faster response, more leads, 24/7 coverage
6. **Call to action** - 15-minute demo or discovery call

### What to AVOID
- Technical jargon (LLMs, APIs, AI models)
- Generic templates
- Long paragraphs
- Multiple CTAs

### What to INCLUDE
- Specific business details from the sheet
- Business outcomes (time saved, leads captured)
- Clear single CTA
- Professional but friendly tone

## Handling Failures

If an email fails to send:
1. Note the failure in the summary report
2. Continue with next lead

## Summary Report

After processing all leads, generate:

| Business Name | Contact Name | Email | Subject | Status |
|---------------|--------------|-------|---------|--------|
| Almira Real Estate | - | info@almira.ae | Subject line | SENT |
| ... | ... | ... | ... | ... |

## Usage Examples

User says:
- "Email the latest leads"
- "Send outreach to 5 new leads"
- "Process unsent leads from the sheet"
- "Email leads that haven't been contacted"

The skill will:
1. Read the sheet
2. Filter unsent leads
3. Process requested number
4. Send personalized emails
5. Generate summary report
