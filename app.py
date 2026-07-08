"""
CRM Hygiene Bot — GTM Demo 3
Upload a dirty contacts CSV → AI cleans and enriches it → download clean CSV + report.
"""

import os
import io
import json
import time
import re
import streamlit as st
import requests
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="CRM Hygiene Bot", page_icon="🧹", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .main { padding-top: 1rem; }
    .stApp { background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%); }
    h1, h2, h3 { color: #f1f5f9 !important; }
    p, li, span { color: #cbd5e1 !important; }
    .result-card {
        background: rgba(30, 41, 59, 0.8);
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .stat-good { color: #10b981 !important; font-weight: 700; font-size: 1.8rem; }
    .stat-bad { color: #f43f5e !important; font-weight: 700; font-size: 1.8rem; }
    .stat-warn { color: #f59e0b !important; font-weight: 700; font-size: 1.8rem; }
    .stat-label { color: #94a3b8 !important; font-size: 0.85rem; }
    [data-testid="stMetricValue"] { color: #10b981 !important; font-size: 1.5rem !important; }
    [data-testid="stMetricLabel"] { color: #94a3b8 !important; }
    section[data-testid="stSidebar"] { background: #0f172a !important; }
    .stButton > button {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        color: white !important; border: none !important;
        padding: 0.6rem 2rem !important; font-weight: 600 !important;
        border-radius: 8px !important; width: 100%;
    }
    .stButton > button:hover { background: linear-gradient(135deg, #059669, #047857) !important; }
    .issue-tag {
        display: inline-block; background: rgba(244, 63, 94, 0.15);
        border: 1px solid rgba(244, 63, 94, 0.3); border-radius: 6px;
        padding: 0.15rem 0.5rem; font-size: 0.75rem; color: #fb7185 !important;
    }
</style>
""", unsafe_allow_html=True)


def get_key(name, sidebar_value):
    if sidebar_value:
        return sidebar_value
    try:
        return st.secrets[name]
    except Exception:
        return ""


def fix_name(name):
    if not name or not isinstance(name, str):
        return name
    return " ".join(w.capitalize() for w in name.strip().split())


def standardize_phone(phone):
    if not phone or not isinstance(phone, str):
        return phone
    digits = re.sub(r'[^\d]', '', str(phone))
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == '1':
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone


def validate_email(email):
    if not email or not isinstance(email, str):
        return {"valid": False, "issue": "Missing email"}
    email = email.strip().lower()
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return {"valid": True, "cleaned": email}
    return {"valid": False, "issue": "Invalid format"}


def find_duplicates(df):
    duplicates = []
    if 'email' in df.columns:
        ec = df['email'].str.lower().str.strip()
        ed = ec[ec.duplicated(keep=False) & ec.notna() & (ec != '')]
        for email in ed.unique():
            idx = df[ec == email].index.tolist()
            duplicates.append({"type": "Email duplicate", "value": email, "rows": [i+2 for i in idx]})
    name_cols = [c for c in df.columns if c in ['name','full_name','fullname','contact_name','first_name']]
    if name_cols:
        nc = df[name_cols[0]].str.lower().str.strip()
        nd = nc[nc.duplicated(keep=False) & nc.notna() & (nc != '')]
        for name in nd.unique():
            idx = df[nc == name].index.tolist()
            if len(idx) > 1:
                duplicates.append({"type": "Name duplicate", "value": name, "rows": [i+2 for i in idx]})
    return duplicates


def clean_dataframe(df):
    cleaned = df.copy()
    issues = []
    fixes = 0
    cleaned.columns = [c.strip().lower().replace(' ', '_') for c in cleaned.columns]
    
    name_cols = [c for c in cleaned.columns if c in ['name','full_name','fullname','contact_name','first_name','last_name','firstname','lastname']]
    email_cols = [c for c in cleaned.columns if 'email' in c]
    phone_cols = [c for c in cleaned.columns if c in ['phone','phone_number','mobile','telephone','cell']]
    company_cols = [c for c in cleaned.columns if c in ['company','company_name','organization','org']]
    
    for col in name_cols:
        for idx, val in cleaned[col].items():
            if pd.notna(val) and isinstance(val, str):
                fixed = fix_name(val)
                if fixed != val:
                    issues.append({"row": idx+2, "field": col, "issue": "Bad capitalization", "before": val, "after": fixed})
                    cleaned.at[idx, col] = fixed
                    fixes += 1
    
    for col in email_cols:
        for idx, val in cleaned[col].items():
            if pd.notna(val) and isinstance(val, str):
                r = validate_email(val)
                if r["valid"] and r["cleaned"] != val:
                    issues.append({"row": idx+2, "field": col, "issue": "Email formatting", "before": val, "after": r["cleaned"]})
                    cleaned.at[idx, col] = r["cleaned"]
                    fixes += 1
                elif not r["valid"]:
                    issues.append({"row": idx+2, "field": col, "issue": r["issue"], "before": val, "after": "Needs review"})
            elif pd.isna(val) or val == '':
                issues.append({"row": idx+2, "field": col, "issue": "Missing email", "before": "(empty)", "after": "Needs review"})
    
    for col in phone_cols:
        for idx, val in cleaned[col].items():
            if pd.notna(val) and isinstance(val, str):
                fixed = standardize_phone(val)
                if fixed != val:
                    issues.append({"row": idx+2, "field": col, "issue": "Phone format", "before": val, "after": fixed})
                    cleaned.at[idx, col] = fixed
                    fixes += 1
    
    for col in name_cols + email_cols + company_cols:
        missing = cleaned[col].isna().sum() + (cleaned[col] == '').sum()
        if missing > 0:
            issues.append({"row": "Multiple", "field": col, "issue": f"{missing} empty values", "before": "(empty)", "after": "Needs data"})
    
    duplicates = find_duplicates(cleaned)
    return cleaned, issues, duplicates, fixes


def ai_analyze(df, issues, duplicates, api_key):
    url = "https://api.anthropic.com/v1/messages"
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
    
    sample = df.head(10).to_csv(index=False)
    issue_summary = {}
    for i in issues:
        t = i["issue"]
        issue_summary[t] = issue_summary.get(t, 0) + 1
    
    prompt = f"""Analyze this CRM data quality report.

DATA: {len(df)} contacts, columns: {list(df.columns)}
Sample:
{sample}

ISSUES: {json.dumps(issue_summary)}
DUPLICATES: {len(duplicates)} found

Return ONLY JSON (no fences):
{{"health_score": 0-100, "health_label": "Good/Needs Work/Critical", "summary": "2-3 sentences about data quality", "top_issues": ["issue1","issue2","issue3"], "enrichment_suggestions": ["suggestion1","suggestion2"]}}"""

    payload = {"model": "claude-haiku-4-5-20251001", "max_tokens": 512, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        if content.startswith("json"):
            content = content[4:].strip()
        return json.loads(content)
    except Exception as e:
        return {"health_score": 0, "health_label": "Error", "summary": f"AI analysis failed: {str(e)}", "top_issues": [], "enrichment_suggestions": []}


def generate_demo_csv():
    return """name,email,phone,company,title,industry
john smith,john.smith@acme.com,1234567890,acme corp,Sales Manager,Technology
SARAH JOHNSON,sarah.johnson@techstart.io,(555) 123-4567,TechStart,VP Marketing,
john smith,john.smith@acme.com,123-456-7890,Acme Corp,Sales Manager,Technology
mike,,5551234567,,Developer,
Jessica Lee,jessica.lee@@notion.com,555.987.6543,Notion,Product Manager,Software
BOB WILSON,bob.wilson@salesforce.com,,Salesforce,Account Executive,Technology
,amy.chen@hubspot.com,(555) 234-5678,HubSpot,SDR,Software
rachel Green,rachel.green@stripe.com,5559876543,stripe,Head of Sales,Fintech
DAVID PARK,david.park@figma.com,(555) 345-6789,Figma,Engineering Manager,Design
tom harris,tom.harris@,5551112222,Deel,BDR,HR Tech
Lisa Wang,lisa.wang@rippling.com,555-222-3333,Rippling,VP Operations,HR Tech
james brown,james.brown@slack.com,(555)444-5555,slack,Customer Success,Technology
EMMA DAVIS,emma.davis@linear.com,5556667777,Linear,Product Lead,Software
,unknown@test.com,,,,
alex kim,alex.kim@notion.com,555 888 9999,Notion,Designer,Software"""


# ─── Sidebar ───
with st.sidebar:
    st.markdown("## 🧹 CRM Hygiene Bot")
    st.markdown("---")
    
    # Silently check for secrets
    has_secrets = False
    try:
        has_secrets = bool(st.secrets["CLAUDE_API_KEY"])
    except Exception:
        pass
    
    demo_mode = not has_secrets
    sidebar_claude = ""

    st.markdown("### 📊 How It Works")
    st.caption("1. Upload contacts CSV or use demo data")
    st.caption("2. Auto-scans: names, emails, phones, duplicates")
    st.caption("3. Fixes what it can, flags the rest")
    st.caption("4. AI generates health report")
    st.caption("5. Download cleaned CSV + report")
    st.markdown("---")
    st.markdown("<div style='text-align:center;color:#475569;font-size:0.8rem;'>Powered by Claude AI</div>", unsafe_allow_html=True)


# ─── Main ───
st.markdown(
    "<h1 style='text-align:center;margin-bottom:0;'>🧹 CRM Hygiene Bot</h1>"
    "<p style='text-align:center;color:#10b981 !important;font-size:1.1rem;margin-top:0.25rem;'>"
    "Upload dirty CRM data → auto-clean → download ready-to-import CSV</p>",
    unsafe_allow_html=True)

st.markdown("")
col_upload, col_demo = st.columns([3, 1])
with col_upload:
    uploaded_file = st.file_uploader("Upload contacts CSV", type=["csv"], label_visibility="collapsed")
with col_demo:
    st.markdown("<div style='height:0.1rem'></div>", unsafe_allow_html=True)
    use_demo = st.button("📋 Use Demo Data")

if use_demo:
    st.session_state["demo_csv"] = True

df = None
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.session_state.pop("demo_csv", None)
elif st.session_state.get("demo_csv"):
    df = pd.read_csv(io.StringIO(generate_demo_csv()))

if df is not None:
    start_time = time.time()

    with st.expander("📄 Original Data", expanded=False):
        st.dataframe(df, use_container_width=True)

    with st.status("🧹 Cleaning CRM data...", expanded=True) as status:
        st.write("🔍 Scanning for issues...")
        cleaned_df, issues, duplicates, fixes_applied = clean_dataframe(df)

        st.write("🤖 AI analyzing data quality...")
        claude_key = get_key("CLAUDE_API_KEY", sidebar_claude)
        if claude_key:
            ai_report = ai_analyze(cleaned_df, issues, duplicates, claude_key)
        else:
            time.sleep(0.5)
            total = len(df)
            ic = len(issues)
            score = max(0, 100 - int((ic / max(total * 3, 1)) * 100))
            ai_report = {
                "health_score": score,
                "health_label": "Good" if score >= 80 else ("Needs Work" if score >= 50 else "Critical"),
                "summary": f"Found {ic} issues across {total} contacts. {fixes_applied} auto-fixed. Add Claude API key for AI recommendations.",
                "top_issues": [f"{fixes_applied} formatting issues auto-fixed", f"{len(duplicates)} duplicates detected", "Review flagged items manually"],
                "enrichment_suggestions": ["Add Claude API key for smart analysis"],
            }

        elapsed = time.time() - start_time
        status.update(label=f"✅ Cleaning complete in {elapsed:.1f}s", state="complete", expanded=False)

    st.markdown("")
    score = ai_report.get("health_score", 0)
    label = ai_report.get("health_label", "Unknown")
    sc = "stat-good" if score >= 80 else ("stat-warn" if score >= 50 else "stat-bad")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown(f"<p class='stat-label'>Health Score</p><p class='{sc}'>{score}/100</p>", unsafe_allow_html=True)
    m2.metric("📊 Contacts", len(df))
    m3.metric("🔧 Auto-Fixed", fixes_applied)
    m4.metric("⚠️ Issues", len(issues))
    m5.metric("👥 Duplicates", len(duplicates))

    st.markdown("")
    st.markdown(f'<div class="result-card"><h3>🤖 AI Analysis: {label}</h3><p>{ai_report.get("summary","")}</p></div>', unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        st.markdown("### 🚨 Top Issues")
        for i, issue in enumerate(ai_report.get("top_issues", []), 1):
            st.markdown(f"**{i}.** {issue}")
        st.markdown("")
        st.markdown("### 💡 Recommendations")
        for s in ai_report.get("enrichment_suggestions", []):
            st.markdown(f"• {s}")

    with right:
        st.markdown("### 🔧 Fix Log")
        if issues:
            fd = [{"Row": i["row"], "Field": i["field"], "Issue": i["issue"], "Before": str(i["before"])[:30], "After": str(i["after"])[:30]} for i in issues[:20]]
            st.dataframe(pd.DataFrame(fd), use_container_width=True, hide_index=True)
            if len(issues) > 20:
                st.caption(f"...and {len(issues)-20} more. Download full report below.")
        else:
            st.success("No issues found — data is clean! 🎉")
        if duplicates:
            st.markdown("### 👥 Duplicates")
            for d in duplicates:
                st.markdown(f"<span class='issue-tag'>{d['type']}</span> **{d['value']}** — rows {', '.join(str(r) for r in d['rows'])}", unsafe_allow_html=True)

    st.markdown("")
    st.markdown("---")
    dl1, dl2, dl3 = st.columns(3)
    with dl1:
        st.download_button("📥 Download Cleaned CSV", data=cleaned_df.to_csv(index=False), file_name=f"cleaned_contacts_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
    with dl2:
        report = {"report_date": datetime.now().isoformat(), "total_contacts": len(df), "health_score": score, "fixes_applied": fixes_applied, "issues": issues, "duplicates": duplicates, "ai_analysis": ai_report}
        st.download_button("📥 Download Report (JSON)", data=json.dumps(report, indent=2), file_name=f"crm_report_{datetime.now().strftime('%Y%m%d')}.json", mime="application/json")
    with dl3:
        with st.expander("👁️ Preview Cleaned Data"):
            st.dataframe(cleaned_df, use_container_width=True)

    st.markdown(f"<p style='text-align:center;margin-top:2rem;color:#64748b !important;font-size:0.8rem;'>Cleaned {len(df)} contacts in {elapsed:.1f}s · {fixes_applied} auto-fixes<br>⚠️ Always review changes before importing to your CRM.</p>", unsafe_allow_html=True)
