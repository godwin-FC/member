# -------------------------
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import altair as alt

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title="Membership Tracker — Business Edition", layout="wide")
DATA_FILE = "members.csv"
PLANS_FILE = "plans.csv"
DATE_FORMAT = "%Y-%m-%d"

DEFAULT_PLANS = {"Bronze":3,"Silver":6,"Gold":9,"Platinum":12}

# -------------------------
# Utilities
# -------------------------
def ensure_files_exist():
    if not os.path.exists(DATA_FILE):
        df = pd.DataFrame(columns=["Member ID","Name","Email","Phone","Start Date","End Date","Plan Type","Status","Notes"])
        df.to_csv(DATA_FILE,index=False)
    if not os.path.exists(PLANS_FILE):
        pd.DataFrame([{"Plan":p,"DurationMonths":m} for p,m in DEFAULT_PLANS.items()]).to_csv(PLANS_FILE,index=False)

def load_members():
    df = pd.read_csv(DATA_FILE,dtype=str)
    for col in ["Start Date","End Date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col],errors="coerce").dt.date
        else:
            df[col] = pd.NaT
    return df

def save_members(df):
    df = df.copy()
    for col in ["Start Date","End Date"]:
        df[col] = df[col].apply(lambda x: x.strftime(DATE_FORMAT) if pd.notna(x) and isinstance(x,date) else (str(x) if pd.notna(x) else ""))
    df.to_csv(DATA_FILE,index=False)

def load_plans():
    df = pd.read_csv(PLANS_FILE,dtype={"Plan":str,"DurationMonths":int})
    return dict(zip(df["Plan"],df["DurationMonths"]))

def save_plans(plans_dict):
    pd.DataFrame([{"Plan":p,"DurationMonths":m} for p,m in plans_dict.items()]).to_csv(PLANS_FILE,index=False)

def generate_member_id(df):
    existing = df.get("Member ID",pd.Series(dtype=str)).dropna().astype(str)
    nums = [int(v[1:]) for v in existing if v.startswith("M") and v[1:].isdigit()]
    return f"M{max(nums)+1:04d}" if nums else "M001"

def refresh_status(df):
    today = date.today()
    # Ensure End Date is datetime
    df["End Date"] = pd.to_datetime(df["End Date"], errors='coerce')
    
    # Compare using .date()
    df["Status"] = df["End Date"].apply(
        lambda end: "Active" if pd.notna(end) and end.date() >= today 
                    else ("Expired" if pd.notna(end) else "Unknown")
    )
    return df


def plan_end_date(start,plan,plans):
    months = plans.get(plan,12)
    year = start.year + (start.month-1 + months)//12
    month = (start.month-1 + months)%12 + 1
    day = min(start.day,28)
    return date(year,month,day)

# -------------------------
# Load data
# -------------------------
ensure_files_exist()
members = load_members()
plans = load_plans()
members = refresh_status(members)
save_members(members)

# -------------------------
# SESSION STATE INIT
# -------------------------
for key in ["member_id", "name", "email", "phone", "start_date", "plan_choice", "notes", "add_member_reset"]:
    if key not in st.session_state:
        if key == "member_id":
            st.session_state[key] = generate_member_id(members)
        elif key == "start_date":
            st.session_state[key] = date.today()
        elif key == "plan_choice":
            st.session_state[key] = list(plans.keys())[0] if plans else "Bronze"
        elif key == "add_member_reset":
            st.session_state[key] = True
        else:
            st.session_state[key] = ""

# -------------------------
# Layout tabs
# -------------------------
st.title("💼 Membership Tracker — Business Edition")
st.markdown("Manage members, renewals, and quick business KPIs — uses CSV files for storage.")
tabs = st.tabs(["🏠 Dashboard","👥 Members","➕ Add Member","🔁 Renew / Edit","⚙️ Settings"])

# -------------------------
# DASHBOARD
# -------------------------
with tabs[0]:
    st.header("📊 Membership Dashboard")

    # --- Top KPI Metrics ---
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    total = len(members)
    active = len(members[members["Status"] == "Active"]) if total else 0
    expired = len(members[members["Status"] == "Expired"]) if total else 0
    unknown = len(members[members["Status"] == "Unknown"]) if total else 0
    retention_rate = (active / total * 100) if total else 0

    # New signups this month
    today = date.today()
    if not members.empty:
        start_dates = pd.to_datetime(members["Start Date"], errors="coerce").dt.date
        this_month = members[
            (start_dates.notna())
            & (pd.Series(start_dates).apply(lambda d: d.month) == today.month)
            & (pd.Series(start_dates).apply(lambda d: d.year) == today.year)
        ]
        new_signups = len(this_month)
    else:
        new_signups = 0

    col1.metric("👥 Total Members", total)
    col2.metric("✅ Active", active)
    col3.metric("⏳ Expired", expired)
    col4.metric("❓ Unknown", unknown)
    col5.metric("📈 Retention Rate", f"{retention_rate:.1f}%")
    col6.metric("🆕 New Signups", new_signups)

    st.divider()

    # --- Quick Charts ---
    st.subheader("📈 Quick Charts")
    c1, c2 = st.columns([1, 2])

    if not members.empty:
        # Plan type chart
        plan_counts = (
            members["Plan Type"]
            .value_counts()
            .rename_axis("Plan")
            .reset_index(name="Count")
        )
        chart1 = (
            alt.Chart(plan_counts)
            .mark_bar(color="#4C78A8")
            .encode(
                x=alt.X("Plan:N", sort="-y", title="Plan Type"),
                y=alt.Y("Count:Q", title="Members"),
                tooltip=["Plan", "Count"]
            )
        )
        c1.altair_chart(chart1, width='content')

        # Monthly renewals (last 12 months)
        last_12 = today - timedelta(days=365)
        end_dates = pd.to_datetime(members["End Date"], errors="coerce")
        df_ends = pd.DataFrame({"end": end_dates})
        df_ends = df_ends[df_ends["end"] >= pd.Timestamp(last_12)]

        if not df_ends.empty:
            df_ends["month"] = df_ends["end"].dt.to_period("M").dt.to_timestamp()
            monthly = df_ends.groupby("month").size().reset_index(name="Count")

            chart2 = (
                alt.Chart(monthly)
                .mark_line(point=True, color="#F58518")
                .encode(
                    x=alt.X("month:T", title="Month"),
                    y=alt.Y("Count:Q", title="Renewals"),
                    tooltip=["month", "Count"]
                )
            )
            c2.altair_chart(chart2, width='content')
        else:
            c2.info("ℹ️ No renewal data in the last 12 months.")
    else:
        c1.info("ℹ️ No members to show charts yet.")
        c2.info("ℹ️ No members to show charts yet.")

    st.divider()

    # --- Retention & Churn Trend ---
    st.subheader("📊 Retention & Churn Trend (Last 12 Months)")
    if not members.empty:
        members["Start Date"] = pd.to_datetime(members["Start Date"], errors="coerce")
        members["End Date"] = pd.to_datetime(members["End Date"], errors="coerce")

        last_12 = today - timedelta(days=365)
        months = pd.date_range(start=last_12, end=today, freq="M")
        retention_data = []
        for m in months:
            total_at_month = members[members["Start Date"] <= m].shape[0]
            active_at_month = members[
                (members["Start Date"] <= m) & (members["End Date"] >= m)
            ].shape[0]
            retention_pct = (active_at_month / total_at_month * 100) if total_at_month else 0
            churn_pct = 100 - retention_pct if total_at_month else 0
            retention_data.append({"month": m, "Retention": retention_pct, "Churn": churn_pct})

        df_retention = pd.DataFrame(retention_data)

        if not df_retention.empty:
            chart3 = (
                alt.Chart(df_retention)
                .transform_fold(["Retention", "Churn"], as_=["Metric", "Value"])
                .mark_line(point=True)
                .encode(
                    x=alt.X("month:T", title="Month"),
                    y=alt.Y("Value:Q", title="Percentage"),
                    color=alt.Color(
                        "Metric:N",
                        scale=alt.Scale(
                            domain=["Retention", "Churn"],
                            range=["#54A24B", "#E45756"]
                        )
                    ),
                    tooltip=["month:T", "Metric:N", alt.Tooltip("Value:Q", format=".1f")]
                )
            )
            st.altair_chart(chart3, width='content')
        else:
            st.info("ℹ️ Not enough data to calculate retention trend.")
    else:
        st.info("ℹ️ No members to calculate retention trend.")

# -------------------------
# MEMBERS
# -------------------------
with tabs[1]:
    st.header("All Members")
    st.write("Search, filter, export and quick actions")

    col_filter1, col_filter2, col_filter3 = st.columns([2, 2, 1])
    search = col_filter1.text_input("Search name / email / phone")
    status_filter = col_filter2.selectbox("Status", options=["All", "Active", "Expired", "Unknown"])
    plan_filter = col_filter3.selectbox("Plan", options=["All"] + sorted(list(plans.keys())))

    df_view = members.copy()
    if search:
        s = search.lower()
        df_view = df_view[df_view.apply(lambda r: s in str(r['Name']).lower() or s in str(r['Email']).lower() or s in str(r['Phone']).lower(), axis=1)]
    if status_filter != "All":
        df_view = df_view[df_view['Status'] == status_filter]
    if plan_filter != "All":
        df_view = df_view[df_view['Plan Type'] == plan_filter]

    st.dataframe(df_view.sort_values('End Date').reset_index(drop=True))

    # Export filtered
    csv = df_view.to_csv(index=False).encode('utf-8')
    st.download_button("Export filtered CSV", data=csv, file_name="members_filtered.csv", mime='text/csv')

    st.markdown("---")
    st.subheader("Delete a member")
    if not members.empty:
        to_delete = st.selectbox("Select member to delete (by ID)", options=members['Member ID'].tolist())
        if st.button("Delete Member"):
            members = members[members['Member ID'] != to_delete]
            save_members(members)
            st.success(f"Member {to_delete} deleted.")
            st.rerun()
    else:
        st.info("No members to delete.")

    st.subheader("Expiring Soon")
    if not members.empty:
        soon = date.today() + timedelta(days=30)
        end_dates = pd.to_datetime(members["End Date"], errors='coerce').dt.date
        expiring_soon = members[end_dates.notna() & (end_dates <= soon)]
        if not expiring_soon.empty:
            st.dataframe(expiring_soon.sort_values("End Date", na_position='last').reset_index(drop=True))
        else:
            st.info("No members expiring in the next 30 days.")
    else:
        st.info("No members in the system.")

        
with tabs[2]:
    st.subheader("➕ Add New Member")

    # Reset form fields if flagged
    if 'add_member_reset' not in st.session_state:
        st.session_state['add_member_reset'] = True

    if st.session_state['add_member_reset']:
        st.session_state['member_id'] = generate_member_id(members)
        st.session_state['name'] = ""
        st.session_state['email'] = ""
        st.session_state['phone'] = ""
        st.session_state['start_date'] = date.today()
        st.session_state['plan_choice'] = list(plans.keys())[0]
        st.session_state['notes'] = ""
        st.session_state['add_member_reset'] = False

    # Main form container
    with st.container():
        st.info("Fill in the details below to register a new member.", icon="📝")

        # Split into two columns for cleaner layout
        col1, col2 = st.columns(2)

        with col1:
            member_id = st.text_input(
                "Member ID",
                value=st.session_state['member_id'],
                key="member_id",
                help="Leave blank to auto-generate a unique ID."
            )
            name = st.text_input(
                "Full Name",
                value=st.session_state['name'],
                key="name"
            )
            email = st.text_input(
                "Email",
                value=st.session_state['email'],
                key="email"
            )
            phone = st.text_input(
                "Phone",
                value=st.session_state['phone'],
                key="phone"
            )

        with col2:
            start_date = st.date_input(
                "Start Date",
                value=st.session_state['start_date'],
                key="start_date"
            )
            plan_choice = st.selectbox(
                "Plan Type",
                options=list(plans.keys()),
                index=list(plans.keys()).index(st.session_state['plan_choice']),
                key="plan_choice"
            )

            # Dynamically calculate End Date
            end_date_auto = plan_end_date(start_date, plan_choice, plans)
            end_date = st.date_input(
                "End Date",
                value=end_date_auto,
                help="Automatically calculated from Start Date + Plan, but can be adjusted."
            )
            st.caption(f"📅 Auto-calculated end date: **{end_date_auto}**")

        st.divider()

        notes = st.text_area(
            "Notes (optional)",
            value=st.session_state['notes'],
            key="notes",
            placeholder="Add any special remarks or conditions here..."
        )

        # Action button
        add_btn = st.button("✅ Add Member", width='content')

        if add_btn:
            # Validations
            if not member_id.strip() or not name.strip():
                st.error("⚠️ Member ID and Full Name are required.")
            elif email.strip() and email.strip().lower() in members['Email'].dropna().str.lower().tolist():
                st.error("⚠️ Email already exists in the system.")
            elif member_id.strip() in members['Member ID'].astype(str).tolist():
                st.error("⚠️ Member ID already exists. Pick another or leave blank to auto-generate.")
            else:
                new = {
                    'Member ID': member_id.strip(),
                    'Name': name.strip(),
                    'Email': email.strip(),
                    'Phone': phone.strip(),
                    'Start Date': start_date,
                    'End Date': end_date,
                    'Plan Type': plan_choice,
                    'Status': 'Active' if end_date >= date.today() else 'Expired',
                    'Notes': notes.strip()
                }
                members = pd.concat([members, pd.DataFrame([new])], ignore_index=True)
                save_members(members)
                st.success(f"🎉 Member **{name}** added with ID **{member_id}**.")

                # Reset form
                st.session_state['add_member_reset'] = True
                st.rerun()

# -------------------------
# RENEW / EDIT
# -------------------------
with tabs[3]:
    st.subheader("🔄 Renew or Edit Member")

    if members.empty:
        st.info("No members available. Add members first.")
    else:
        # Member selector
        member_id_sel = st.selectbox(
            "Select Member",
            options=members['Member ID'].tolist(),
            help="Choose a member to view and edit details."
        )
        sel_row = members[members['Member ID'] == member_id_sel].iloc[0]

        # Current info card
        st.markdown("### 📋 Current Information")
        st.dataframe(
            sel_row[['Member ID', 'Name', 'Email', 'Phone', 'Start Date',
                     'End Date', 'Plan Type', 'Status', 'Notes']].to_frame().T,
         width='content'
        )

        st.divider()

        # Edit form
        with st.form("edit_member_form"):
            st.markdown("### ✏️ Edit Details")

            # Split into two columns for cleaner layout
            col1, col2 = st.columns(2)

            with col1:
                name = st.text_input("Full Name", value=sel_row['Name'])
                email = st.text_input("Email", value=sel_row['Email'])
                phone = st.text_input("Phone", value=sel_row['Phone'])
                start_date = st.date_input(
                    "Start Date",
                    value=sel_row['Start Date'] if pd.notna(sel_row['Start Date']) else date.today()
                )

            with col2:
                plan_choice = st.selectbox(
                    "Plan Type",
                    options=list(plans.keys()),
                    index=list(plans.keys()).index(sel_row['Plan Type']) if sel_row['Plan Type'] in plans else 0
                )
                end_date = st.date_input(
                    "End Date",
                    value=sel_row['End Date'] if pd.notna(sel_row['End Date']) else plan_end_date(start_date, plan_choice, plans)
                )
                notes = st.text_area("Notes", value=sel_row.get('Notes', ''))

            st.divider()

            # Quick renew options
            st.markdown("### ⚡ Quick Renew")
            col_a, col_b = st.columns([2, 1])
            with col_a:
                renew_months = st.number_input(
                    "Renew for how many months?",
                    min_value=0, max_value=60, value=0, step=1,
                    help="Enter number of months to extend membership."
                )
            with col_b:
                apply_quick = st.checkbox("Apply quick renew")

            st.divider()

            # Save button
            save_btn = st.form_submit_button("💾 Save Changes", width='content')

            if save_btn:
                # apply quick renew by adding months to current end_date
                new_end = end_date
                if apply_quick and renew_months > 0:
                    base = sel_row['End Date'] if pd.notna(sel_row['End Date']) else date.today()
                    year = base.year + (base.month - 1 + renew_months) // 12
                    month = (base.month - 1 + renew_months) % 12 + 1
                    day = min(base.day, 28)
                    new_end = date(year, month, day)

                members.loc[members['Member ID'] == member_id_sel,
                            ['Name', 'Email', 'Phone', 'Start Date', 'End Date', 'Plan Type', 'Notes']] = [
                    name, email, phone, start_date, new_end, plan_choice, notes
                ]
                members = refresh_status(members)
                save_members(members)
                st.success(f"✅ Member **{name}** updated successfully.")
                st.rerun()

# -------------------------
# SETTINGS
# -------------------------
with tabs[4]:
    st.header("Settings — Plans & Durations")
    st.write("Define plans and their default durations (months). These are used as defaults when adding new members.")

    plans_df = pd.DataFrame([{"Plan": p, "DurationMonths": m} for p, m in plans.items()])
    edited = st.data_editor(plans_df, num_rows="dynamic")
    if st.button("Save Plans"):
        # sanitize and save
        new_plans = {row['Plan']: int(row['DurationMonths']) for _, row in edited.iterrows()}
        save_plans(new_plans)
        st.success("Plans saved. New plans will be available when adding members.")
        st.rerun()

    st.markdown("---")
    st.subheader("Manual CSV Management")
    st.write("You can download or upload the members CSV. Use upload cautiously — it will replace current data.")
    dl = st.download_button("Download members CSV", data=members.to_csv(index=False).encode('utf-8'), file_name="members.csv", mime='text/csv')

    uploaded = st.file_uploader("Upload a members CSV to replace current dataset", type=["csv"])
    if uploaded is not None:
        confirm = st.checkbox("I understand this will replace the current members data")
        if confirm:
            new_df = pd.read_csv(uploaded)
            # basic validation
            required = set(["Member ID", "Name", "Start Date", "End Date", "Plan Type"])
            if not required.issubset(set(new_df.columns)):
                st.error(f"Uploaded CSV must contain columns: {required}")
            else:
                # coerce dates
                for col in ["Start Date", "End Date"]:
                    new_df[col] = pd.to_datetime(new_df[col], errors='coerce').dt.date
                new_df = refresh_status(new_df)
                save_members(new_df)
                st.success("Members CSV replaced successfully.")
                st.rerun()

# -------------------------
# END
# -------------------------


# Helpful footer
st.sidebar.markdown("---")
st.sidebar.write("Data file:\\n" + os.path.abspath(DATA_FILE))
st.sidebar.write("Plans file:\\n" + os.path.abspath(PLANS_FILE))
st.sidebar.write("Tips: Back up your CSV files regularly.")
