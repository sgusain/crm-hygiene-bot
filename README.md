# 🧹 CRM Hygiene Bot — GTM Demo

Upload a dirty contacts CSV → bot auto-cleans names, emails, phones, finds duplicates → AI generates health report → download cleaned CSV.

## Quick Start

```bash
pip install streamlit requests pandas
streamlit run app.py
```

Click "Use Demo Data" to see it in action — no API keys needed.

## What It Cleans

- Name capitalization (john smith → John Smith)
- Email validation and formatting
- Phone number standardization → (XXX) XXX-XXXX
- Duplicate detection (email and name based)
- Missing data flagging
- AI-powered health score and recommendations (with Claude API key)

## Works With Any CRM

Export contacts as CSV from HubSpot, Salesforce, Zoho, Pipedrive, or any spreadsheet → upload → clean → re-import.

Powered by Claude AI
