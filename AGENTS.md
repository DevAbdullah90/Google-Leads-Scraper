# Project Agents Guidelines

## Email Sending Rules (Zoho Mail MCP)

When sending emails via Zoho Mail MCP, ALWAYS follow these rules:

### 1. HTML Structure
- Wrap ALL email content in `<html><body>` tags
- Never send plain text content when `mailFormat: "html"` is set

### 2. Line Breaks
- Use `<br>` tags for line breaks, NOT `\n`
- Use `<p>` tags for paragraphs

### 3. HTML Signature
- ALWAYS embed the HTML signature directly in the email content
- NEVER rely on `includeSignature: true` parameter - it does NOT work
- Read the signature from `config/email_signature.html` and append it to the email content

### 4. Correct Email Format Template
```json
{
  "fromAddress": "info@nexeagent.com",
  "toAddress": "recipient@example.com",
  "subject": "Your Subject Here",
  "content": "<html><body><p>Your email content here.</p><p>Best regards,</p>[INSERT HTML SIGNATURE HERE]</body></html>",
  "mailFormat": "html"
}
```

### 5. Example of Correct Content
```html
<html>
<body>
<p>Dear Contact,</p>
<p>Your email body text goes here.</p>
<p>Best regards,</p>
<div style="font-family:Arial, sans-serif; font-size:13px; color:rgb(51, 51, 51); line-height:1.6; max-width:480px">
<!-- Signature HTML from config/email_signature.html goes here -->
</div>
</body>
</html>
```

### 6. Key Points to Remember
- `includeSignature: true` does NOT work - always embed signature manually
- Content MUST be wrapped in `<html><body>` tags
- Use `<br>` for line breaks, not `\n`
- Use `<p>` tags for paragraphs
- The signature file is located at `config/email_signature.html`

## Zoho Mail Account
- Account ID: `6031472000000008002`
- From Address: `info@nexeagent.com`
