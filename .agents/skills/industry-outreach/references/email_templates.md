# Email Templates

All templates use the same personalization tokens:
- `{business_name}`, `{rating}`, `{review_count}`, `{location}`, `{category}`
- `{pain_hook}` — specific pain point mined from reviews
- `{signature}` — HTML signature from `config/email_signature.html`

Wrap ALL content in `<html><body>` tags. Use `<br>` for line breaks, `<p>` for paragraphs.

---

## Healthcare Templates

### Initial Email — Pain-Point Hook (Review-Based)

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I read through some of your Google reviews and noticed a patient mentioned {pain_hook}. That's a common challenge busy practices face — your front desk team is juggling check-ins, phone calls, and paperwork all at once.</p>

<p>We've built a smart assistant that handles appointment booking instantly — patients can schedule, reschedule, or cancel appointments without calling in. It answers common questions about services, insurance, and office hours 24/7, so your staff can focus on the patients in front of them.</p>

<p>Clinics using this system report fewer no-shows (thanks to automated reminders), shorter phone hold times, and happier patients who appreciate the instant responses.</p>

<p>Would you be open to a 15-minute call to see how this could work for {business_name}?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Initial Email — Rating + Reviews Hook

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>Your {rating} rating with {review_count} reviews is impressive — it's clear your patients value the care you provide at {location}.</p>

<p>One thing many practices like yours struggle with is keeping up with phone inquiries during peak hours. Every missed call is a potential patient who moves on to another provider.</p>

<p>We've developed an AI receptionist that answers every call instantly — even after hours. It books appointments, answers FAQs about services and insurance, and routes urgent calls to the right person. Your team stays focused on patient care while no inquiry slips through the cracks.</p>

<p>Could we schedule a quick demo to show you how it works?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Initial Email — Short & Direct

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>Quick question: how many phone calls does your front desk miss during a typical day?</p>

<p>We help healthcare practices capture every inquiry with a smart assistant that books appointments, answers patient questions, and sends reminders — all without adding to your team's workload.</p>

<p>Worth a 15-minute conversation?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #1 (Day 3) — Gentle Reminder

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I reached out a few days ago about helping {business_name} automate appointment booking and patient inquiries. I know things get busy, so I wanted to follow up.</p>

<p>Based on your {review_count} Google reviews, I noticed patients specifically mention {original_pain_hook}. Our smart assistant directly addresses this — it handles scheduling, answers FAQs, and responds to patients instantly, even after hours.</p>

<p>Would a quick 15-minute call work this week to explore if this fits {business_name}?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #2 (Day 7) — Different Angle + Urgency

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I wanted to circle back on my earlier note. In the healthcare space, every missed call is a patient who might book with a competitor instead.</p>

<p>I noticed from your reviews that {original_pain_hook}. Our smart assistant eliminates this gap — it answers every call, books appointments, and sends reminders automatically. Your front desk stays focused on in-person care while no inquiry slips through.</p>

<p>Many similar practices have seen 30% fewer missed calls within the first month. Happy to share how — would a 15-minute demo work?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #3 (Day 14) — Final Attempt

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>This is my last note — I don't want to take up too much of your time.</p>

<p>If patient scheduling and missed calls are still a challenge at {business_name}, I'd love to show you how our smart assistant has helped similar practices reduce missed inquiries by 30% and cut phone hold times in half.</p>

<p>No pressure at all — if the timing isn't right, I completely understand. But if you're open to a quick 15-minute chat, just reply to this email and I'll set it up.</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

---

## Education Templates

### Initial Email — Pain-Point Hook (Review-Based)

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I came across your Google listing and noticed a reviewer mentioned {original_pain_hook}. That's a challenge many education institutions face — admissions teams are drowning in paperwork while prospective families are browsing alternatives.</p>

<p>We've built a smart assistant that responds to parent and student inquiries instantly — 24/7. It answers questions about programs, fees, enrollment deadlines, and schedules campus visits. When a parent is ready to enroll, your admissions team gets a qualified lead instead of playing email tag.</p>

<p>Schools using this system see faster enrollment conversions, fewer missed inquiries, and parents who appreciate the instant, helpful responses.</p>

<p>Would you be open to a 15-minute call to see how this could work for {business_name}?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Initial Email — Enrollment Focus

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>With {review_count} reviews and a {rating} rating, {business_name} clearly delivers quality education at {location}. The challenge isn't attracting interest — it's converting inquiries into enrollments before families look elsewhere.</p>

<p>We've developed an AI assistant that handles the entire inquiry-to-enrollment journey. It responds to questions about programs, fees, and availability instantly, guides parents through the application process, and sends automated follow-ups to keep your institution top of mind.</p>

<p>The result: more completed enrollments, less time spent on repetitive admin, and a smoother experience for prospective families.</p>

<p>Could we schedule a quick 15-minute demo?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Initial Email — Short & Direct

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>How quickly does your team respond to new parent inquiries?</p>

<p>In our experience, the first institution to respond usually wins the enrollment. We've built a smart assistant that replies to every inquiry instantly — answering program questions, sharing fee details, and scheduling campus tours.</p>

<p>Worth a quick conversation?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #1 (Day 3) — Gentle Reminder

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I reached out a few days ago about helping {business_name} respond to enrollment inquiries instantly. I know things get busy during the school year, so I wanted to follow up.</p>

<p>I noticed from your Google reviews that {original_pain_hook}. Our smart assistant directly addresses this — it answers parent questions 24/7, sends program details, and books campus visits automatically.</p>

<p>Would a quick 15-minute call work this week to explore if this fits {business_name}?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #2 (Day 7) — Different Angle + Urgency

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I wanted to circle back on my earlier note. In education, the first institution to respond to an inquiry usually wins the enrollment.</p>

<p>I noticed from your reviews that {original_pain_hook}. Our smart assistant eliminates this gap — it responds to every parent inquiry instantly, answers program questions, and schedules tours without any manual effort from your team.</p>

<p>Institutions using this system see 40% faster inquiry-to-enrollment conversion. Happy to share how — would a 15-minute demo work?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #3 (Day 14) — Final Attempt

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>This is my last note — I don't want to take up too much of your time.</p>

<p>If managing enrollment inquiries is still a challenge at {business_name}, I'd love to show you how similar institutions have increased enrollment conversions by 40% with a smart assistant that responds to every parent instantly.</p>

<p>No pressure at all — if the timing isn't right, I completely understand. But if you're open to a quick 15-minute chat, just reply to this email and I'll set it up.</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

---

## Real Estate Templates

### Initial Email — Pain-Point Hook (Review-Based)

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I read through some of your Google reviews and noticed a client mentioned {original_pain_hook}. In Abu Dhabi's competitive real estate market, that delayed response often means losing the client to another agency.</p>

<p>We've built a smart WhatsApp assistant that responds to every property inquiry instantly — 24/7. It answers questions about listings, shares property details and pricing, and qualifies leads before handing off to your sales team. When a client is ready for a viewing, your agent gets notified immediately.</p>

<p>Agencies using this system report faster response times, more completed viewings, and better client satisfaction — all from their existing WhatsApp number.</p>

<p>Would you be open to a 15-minute call to see how this could work for {business_name}?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Initial Email — Rating + Reviews Hook

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I came across your Google listing and was impressed by your {rating} rating with {review_count} reviews — that's a clear sign clients trust your expertise in {location} real estate.</p>

<p>However, I noticed a common challenge many agencies face: WhatsApp inquiries that come in after hours or during busy periods often get delayed responses. In real estate, speed matters — the first agency to respond usually wins the client.</p>

<p>We've built a smart WhatsApp assistant specifically for real estate agencies like yours. It instantly replies to every property inquiry 24/7, answers questions about listings, shares property details, and qualifies leads automatically.</p>

<p>Could we schedule a quick 15-minute demo to show you how it works?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Initial Email — Short & Direct

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>Quick question: How quickly does your team respond to WhatsApp property inquiries?</p>

<p>In real estate, the gap between inquiry and response often determines whether you win or lose a client. We've built a smart assistant that responds to every WhatsApp message instantly — 24/7.</p>

<p>Worth a 15-minute conversation?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #1 (Day 3) — Gentle Reminder

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I reached out a few days ago about helping {business_name} capture every WhatsApp inquiry instantly. I know things get busy with viewings and client meetings, so I wanted to follow up.</p>

<p>I noticed from your Google reviews that {original_pain_hook}. Our smart WhatsApp assistant directly addresses this — it responds to every property inquiry 24/7, shares listings, and books viewings automatically.</p>

<p>Would a quick 15-minute call work this week to explore if this fits {business_name}?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #2 (Day 7) — Different Angle + Urgency

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>I wanted to circle back on my earlier note. In Abu Dhabi's real estate market, every missed WhatsApp inquiry is a potential commission lost to a competitor.</p>

<p>I noticed from your reviews that {original_pain_hook}. Our smart assistant eliminates this gap — it responds to every inquiry instantly, shares property details, and qualifies leads before handing off to your sales team.</p>

<p>Agencies using this system report 35% more completed viewings from the same lead volume. Happy to share how — would a 15-minute demo work?</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

### Follow-Up #3 (Day 14) — Final Attempt

```
<html>
<body>
<p>Dear {business_name} Team,</p>

<p>This is my last note — I don't want to take up too much of your time.</p>

<p>If missed WhatsApp leads are still a challenge at {business_name}, I'd love to show you how similar agencies have increased completed viewings by 35% with a smart assistant that responds to every property inquiry instantly.</p>

<p>No pressure at all — if the timing isn't right, I completely understand. But if you're open to a quick 15-minute chat, just reply to this email and I'll set it up.</p>

<p>Best regards,</p>
{signature}
</body>
</html>
```

---

## Subject Lines

### Healthcare — Initial
- "Help {business_name} patients book appointments without the hold music"
- "{business_name} — your {review_count} patients deserve faster scheduling"
- "Quick question about {business_name}'s phone response times"
- "{business_name} — never miss a patient call again"

### Healthcare — Follow-Ups
- Follow-up #1: "Quick follow-up — {business_name} patient scheduling"
- Follow-up #2: "{business_name} — patients are calling, are you answering?"
- Follow-up #3: "Last note — {business_name} patient booking"

### Education — Initial
- "{business_name} — never miss a parent inquiry again"
- "With {review_count} reviews, {business_name} needs instant enrollment responses"
- "Quick question about {business_name}'s admissions process"
- "{business_name} — capture every enrollment inquiry 24/7"

### Education — Follow-Ups
- Follow-up #1: "Following up — {business_name} enrollment inquiries"
- Follow-up #2: "{business_name} — competitors are responding faster"
- Follow-up #3: "Final follow-up — {business_name} enrollment"

### Real Estate — Initial
- "{business_name} — capture every WhatsApp lead 24/7"
- "{business_name}'s {rating} rating deserves 24/7 WhatsApp support"
- "Quick question about {business_name}'s response times"
- "{business_name} — never miss a property inquiry again"

### Real Estate — Follow-Ups
- Follow-up #1: "Quick follow-up — {business_name} WhatsApp leads"
- Follow-up #2: "{business_name} — every missed WhatsApp = lost commission"
- Follow-up #3: "Closing the loop — {business_name} property inquiries"
