# -------------------------
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import mysql.connector
from mysql.connector import Error
import altair as alt
from dotenv import load_dotenv
import os
# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title="Membership Tracker — MySQL Edition", layout="wide")
# Load environment variables from .env file
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")

# Membership plans
DEFAULT_PLANS = {
    "Bronze": int(os.getenv("PLAN_BRONZE", 3)),
    "Silver": int(os.getenv("PLAN_SILVER", 6)),
    "Gold": int(os.getenv("PLAN_GOLD", 9)),
    "Platinum": int(os.getenv("PLAN_PLATINUM", 12))
}

DATE_FORMAT = os.getenv("DATE_FORMAT", "%Y-%m-%d")
# -------------------------
# MySQL Connection
# -------------------------
try:
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor(buffered=True)
    st.success("✅ Connected to MySQL!")
except Error as e:
    st.error(f"❌ Could not connect to MySQL: {e}")
    st.stop()

# -------------------------
# Ensure tables exist
# -------------------------
def ensure_tables_exist():
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                MemberID VARCHAR(10) PRIMARY KEY,
                Name VARCHAR(255) NOT NULL,
                Email VARCHAR(255),
                Phone VARCHAR(50),
                StartDate DATE,
                EndDate DATE,
                PlanType VARCHAR(50),
                Status VARCHAR(20),
                Notes TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                Plan VARCHAR(50) PRIMARY KEY,
                DurationMonths INT
            )
        """)
        
        # Insert default plans if empty
        cursor.execute("SELECT COUNT(*) FROM plans")
        if cursor.fetchone()[0] == 0:
            for plan, months in DEFAULT_PLANS.items():
                cursor.execute("INSERT INTO plans (Plan, DurationMonths) VALUES (%s, %s)", (plan, months))
            conn.commit()
    except Error as e:
        st.error(f"❌ Error creating tables or inserting default plans: {e}")
        st.stop()

ensure_tables_exist()

# -------------------------
# Load data
# -------------------------
def load_members():
    try:
        cursor.execute("SELECT * FROM members")
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(rows, columns=cols)
        for col in ["StartDate", "EndDate"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        return df
    except Error as e:
        st.error(f"❌ Error loading members: {e}")
        return pd.DataFrame()

def load_plans():
    try:
        cursor.execute("SELECT * FROM plans")
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    except Error as e:
        st.error(f"❌ Error loading plans: {e}")
        return DEFAULT_PLANS.copy()

members = load_members()
plans = load_plans()

# -------------------------
# Utility functions
# -------------------------
def refresh_status(df):
    today = date.today()
    df["Status"] = df["EndDate"].apply(
        lambda x: "Active" if pd.notna(x) and x >= today else ("Expired" if pd.notna(x) else "Unknown")
    )
    return df

def plan_end_date(start, plan_name, plans_dict):
    months = plans_dict.get(plan_name, 12)
    year = start.year + (start.month-1 + months)//12
    month = (start.month-1 + months)%12 + 1
    day = min(start.day, 28)
    return date(year, month, day)

def generate_member_id(df):
    existing = df.get("MemberID", pd.Series(dtype=str)).dropna().astype(str)
    nums = [int(v[1:]) for v in existing if v.startswith("M") and v[1:].isdigit()]
    return f"M{max(nums)+1:04d}" if nums else "M001"

members = refresh_status(members)

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
# Functions for DB Operations with Error Handling
# -------------------------
def add_member_to_db(member_id, name, email, phone, start_date, end_date, plan_choice, notes):
    try:
        status = "Active" if end_date >= date.today() else "Expired"
        cursor.execute("""
            INSERT INTO members (MemberID, Name, Email, Phone, StartDate, EndDate, PlanType, Status, Notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (member_id, name, email, phone, start_date, end_date, plan_choice, status, notes))
        conn.commit()
        st.success(f"Member {name} added successfully!")
    except Error as e:
        st.error(f"❌ Failed to add member: {e}")

def update_member_in_db(member_id, name, email, phone, start_date, end_date, plan_choice, notes):
    try:
        status = "Active" if end_date >= date.today() else "Expired"
        cursor.execute("""
            UPDATE members
            SET Name=%s, Email=%s, Phone=%s, StartDate=%s, EndDate=%s, PlanType=%s, Notes=%s, Status=%s
            WHERE MemberID=%s
        """, (name, email, phone, start_date, end_date, plan_choice, notes, status, member_id))
        conn.commit()
        st.success(f"Member {name} updated successfully!")
    except Error as e:
        st.error(f"❌ Failed to update member: {e}")

def save_plans_to_db(plans_df):
    try:
        for _, row in plans_df.iterrows():
            cursor.execute("REPLACE INTO plans (Plan, DurationMonths) VALUES (%s, %s)", 
                           (row['Plan'], int(row['DurationMonths'])))
        conn.commit()
        st.success("✅ Plans saved successfully!")
    except Error as e:
        st.error(f"❌ Failed to save plans: {e}")

# -------------------------
# LAYOUT
# -------------------------
st.title("💼 Membership Tracker — MySQL Edition")
tabs = st.tabs(["🏠 Dashboard","👥 Members","➕ Add Member","🔁 Renew / Edit","⚙️ Settings"])

with tabs[0]:
    st.header("📊 Membership Dashboard")
    st.markdown("Manage and visualize your memberships at a glance.")

    # --- Filters ---
    colf1, colf2 = st.columns([1,1])
    plan_filter = colf1.selectbox("Filter by Plan", options=["All"] + list(plans.keys()))
    status_filter = colf2.selectbox("Filter by Status", options=["All", "Active", "Expired", "Unknown"])

    df_filtered = members.copy()
    if plan_filter != "All":
        df_filtered = df_filtered[df_filtered["PlanType"] == plan_filter]
    if status_filter != "All":
        df_filtered = df_filtered[df_filtered["Status"] == status_filter]

    # --- KPI Metrics ---
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    total = len(df_filtered)
    active = len(df_filtered[df_filtered["Status"]=="Active"])
    expired = len(df_filtered[df_filtered["Status"]=="Expired"])
    unknown = len(df_filtered[df_filtered["Status"]=="Unknown"])
    retention_rate = (active/total*100) if total else 0

    today = date.today()
    start_dates = pd.to_datetime(df_filtered["StartDate"], errors="coerce")
    this_month = df_filtered[(start_dates.notna()) & 
                             (start_dates.dt.month==today.month) &
                             (start_dates.dt.year==today.year)]
    new_signups = len(this_month)
    
    last_month = (today.replace(day=1)-timedelta(days=1))
    last_month_count = df_filtered[(start_dates.notna()) &
                                   (start_dates.dt.month==last_month.month) &
                                   (start_dates.dt.year==last_month.year)].shape[0]
    delta_signups = new_signups - last_month_count

    # Color-coded metrics
    col1.metric("👥 Total Members", total)
    col2.metric("✅ Active", active, delta=f"{active/total*100:.1f}%" if total else "0%")
    col3.metric("⏳ Expired", expired)
    col4.metric("❓ Unknown", unknown)
    col5.metric("📈 Retention Rate", f"{retention_rate:.1f}%")
    col6.metric("🆕 New Signups", new_signups, delta=f"{delta_signups:+}")

    st.markdown("---")

    # --- Quick Charts ---
    st.subheader("📈 Quick Charts")
    c1, c2 = st.columns([1, 2])

    if not df_filtered.empty:
        # Interactive Plan Chart
        selection = alt.selection_single(fields=["Plan"], bind='legend', empty='all')
        plan_counts = df_filtered["PlanType"].value_counts().rename_axis("Plan").reset_index(name="Count")
        chart1 = (alt.Chart(plan_counts)
                  .mark_bar()
                  .encode(
                      x=alt.X("Plan:N", sort="-y", title="Plan Type"),
                      y=alt.Y("Count:Q", title="Members"),
                      color=alt.Color("Plan:N", legend=None, scale=alt.Scale(scheme="category10")),
                      tooltip=["Plan","Count"],
                      opacity=alt.condition(selection, alt.value(1), alt.value(0.6))
                  ).add_selection(selection))
        c1.altair_chart(chart1, use_container_width=True)

        # Monthly Renewals
        last_12 = today - timedelta(days=365)
        end_dates = pd.to_datetime(df_filtered["EndDate"], errors="coerce")
        df_ends = pd.DataFrame({"end": end_dates})
        df_ends = df_ends[df_ends["end"] >= pd.Timestamp(last_12)]
        if not df_ends.empty:
            df_ends["month"] = df_ends["end"].dt.to_period("M").dt.to_timestamp()
            monthly = df_ends.groupby("month").size().reset_index(name="Count")
            chart2 = (alt.Chart(monthly)
                      .mark_line(point=True, color="#F58518")
                      .encode(
                          x=alt.X("month:T", axis=alt.Axis(format="%b %Y")),
                          y="Count:Q",
                          tooltip=[alt.Tooltip("month:T", format="%b %Y"), "Count"]
                      ))
            c2.altair_chart(chart2, use_container_width=True)
        else:
            c2.info("ℹ️ No renewal data in the last 12 months.")
    else:
        c1.info("ℹ️ No data to show charts.")
        c2.info("ℹ️ No data to show charts.")

    st.markdown("---")

    # --- Retention & Churn with Hover ---
    st.subheader("📊 Retention & Churn Trend (Last 12 Months)")
    if not df_filtered.empty:
        df_filtered["StartDate"] = pd.to_datetime(df_filtered["StartDate"], errors="coerce")
        df_filtered["EndDate"] = pd.to_datetime(df_filtered["EndDate"], errors="coerce")
        months = pd.date_range(start=today-timedelta(days=365), end=today, freq="ME")
        retention_data = []
        for m in months:
            total_at_month = df_filtered[df_filtered["StartDate"]<=m].shape[0]
            active_at_month = df_filtered[(df_filtered["StartDate"]<=m) & (df_filtered["EndDate"]>=m)].shape[0]
            retention_pct = (active_at_month/total_at_month*100) if total_at_month else 0
            churn_pct = 100 - retention_pct if total_at_month else 0
            retention_data.append({"month": m, "Retention": retention_pct, "Churn": churn_pct})
        df_retention = pd.DataFrame(retention_data)
        chart3 = (alt.Chart(df_retention)
                  .transform_fold(["Retention","Churn"], as_=["Metric","Value"])
                  .mark_line(point=True)
                  .encode(
                      x=alt.X("month:T", axis=alt.Axis(format="%b %Y")),
                      y="Value:Q",
                      color=alt.Color("Metric:N", scale=alt.Scale(domain=["Retention","Churn"], range=["#54A24B","#E45756"])),
                      tooltip=["month:T","Metric:N",alt.Tooltip("Value:Q",format=".1f")]
                  ))
        st.altair_chart(chart3, use_container_width=True)


# -------------------------
# MEMBERS (Tab 1)
# -------------------------
with tabs[1]:
    st.header("👥 All Members")
    st.write("Search, filter, export, and manage memberships.")

    # --- Filters ---
    col1, col2, col3 = st.columns([2, 2, 1])
    search = col1.text_input("Search name / email / phone")

    status_filter = col2.multiselect(
        "Status",
        options=["Active", "Expired", "Unknown"],
        default=["Active", "Expired", "Unknown"]
    )

    plan_filter = col3.multiselect(
        "Plan",
        options=sorted(list(plans.keys())),
        default=sorted(list(plans.keys()))
    )

    df_view = members.copy()

    # --- Apply search ---
    if search:
        s = search.lower()
        df_view = df_view[df_view.apply(
            lambda r: s in str(r['Name']).lower() or
                      s in str(r['Email']).lower() or
                      s in str(r['Phone']).lower(),
            axis=1
        )]

    # --- Apply filters ---
    df_view = df_view[df_view['Status'].isin(status_filter)]
    df_view = df_view[df_view['PlanType'].isin(plan_filter)]

    # --- Highlight Expiring Soon ---
    soon = date.today() + timedelta(days=30)
    df_view['ExpiringSoon'] = df_view['EndDate'].apply(lambda x: x <= soon if pd.notna(x) else False)

    # --- Define styling functions ---
    def color_status(val):
        if val == "Active":
            color = "green"
        elif val == "Expired":
            color = "red"
        elif val == "Unknown":
            color = "orange"
        else:
            color = "black"
        return f"color: {color}; font-weight: bold"

    def highlight_expiring(val):
        return "background-color: yellow" if val else ""

    # --- Apply styling ---
    styled_df = (df_view.sort_values('EndDate')
                 .reset_index(drop=True)
                 .style
                 .applymap(color_status, subset=['Status'])
                 .applymap(highlight_expiring, subset=['ExpiringSoon']))

    # --- Display dataframe ---
    st.dataframe(styled_df, use_container_width=True)

    # --- Export filtered CSV ---
    csv = df_view.drop(columns=['ExpiringSoon']).to_csv(index=False).encode('utf-8')
    st.download_button("Export filtered CSV", data=csv, file_name="members_filtered.csv", mime='text/csv')

    st.markdown("---")

    # --- Delete Member ---
    with st.expander("Delete a Member"):
        if not members.empty:
            to_delete = st.selectbox("Select member to delete (by ID)", options=members['MemberID'].tolist())
            if st.button("Delete Member"):
                cursor.execute("DELETE FROM members WHERE MemberID = %s", (to_delete,))
                conn.commit()
                members = load_members()
                st.success(f"Member {to_delete} deleted successfully.")
                st.rerun()
        else:
            st.info("No members to delete.")

    # --- Expiring Soon Table ---
    st.subheader("⚠️ Expiring Soon (Next 30 Days)")
    if not members.empty:
        expiring_soon = members[(members["EndDate"].notna()) & (members["EndDate"] <= soon)]
        if not expiring_soon.empty:
            st.dataframe(expiring_soon.sort_values("EndDate").reset_index(drop=True), use_container_width=True)
        else:
            st.info("No members expiring in the next 30 days.")
    else:
        st.info("No members in the system.")

with tabs[2]:
    st.subheader("➕ Add New Member")
    st.info("Fill in the details below to register a new member.", icon="📝")

    # Reset form fields if flagged
    if 'add_member_reset' not in st.session_state:
        st.session_state['add_member_reset'] = True

    if st.session_state['add_member_reset']:
        st.session_state.update({
            'member_id': generate_member_id(members),
            'name': '',
            'email': '',
            'phone': '',
            'start_date': date.today(),
            'plan_choice': list(plans.keys())[0] if plans else "Bronze",
            'notes': '',
            'add_member_reset': False
        })

    # Use a form for submission
    with st.form("add_member_form", clear_on_submit=False):
        col1, col2 = st.columns(2)

        with col1:
            member_id = st.text_input(
                "Member ID",
                value=st.session_state['member_id'],
                help="Leave blank to auto-generate a unique ID."
            )
            name = st.text_input("Full Name", value=st.session_state['name'])
            email = st.text_input("Email", value=st.session_state['email'])
            phone = st.text_input("Phone", value=st.session_state['phone'])

        with col2:
            start_date = st.date_input("Start Date", value=st.session_state['start_date'])
            plan_choice = st.selectbox(
                "Plan Type",
                options=list(plans.keys()),
                index=list(plans.keys()).index(st.session_state['plan_choice'])
            )

            # Live calculation of End Date
            end_date_auto = plan_end_date(start_date, plan_choice, plans)
            end_date = st.date_input("End Date", value=end_date_auto)
            st.caption(f"📅 Auto-calculated end date: **{end_date_auto}**")

        notes = st.text_area(
            "Notes (optional)",
            value=st.session_state['notes'],
            placeholder="Add any special remarks or conditions here..."
        )

        # Submit button
        submitted = st.form_submit_button("✅ Add Member")

        if submitted:
            # Auto-generate ID if empty
            if not member_id.strip():
                member_id = generate_member_id(members)

            # Validations
            existing_emails = members['Email'].dropna().str.lower().tolist()
            existing_ids = members['MemberID'].astype(str).tolist()

            if not member_id.strip() or not name.strip():
                st.error("⚠️ Member ID and Full Name are required.")
            elif email.strip() and email.strip().lower() in existing_emails:
                st.error("⚠️ Email already exists in the system.")
            elif member_id.strip() in existing_ids:
                st.error("⚠️ Member ID already exists. Pick another or leave blank to auto-generate.")
            else:
                # Add to DB
                add_member_to_db(
                    member_id.strip(),
                    name.strip(),
                    email.strip(),
                    phone.strip(),
                    start_date,
                    end_date,
                    plan_choice,
                    notes.strip()
                )

                # Refresh local DataFrame
                members = load_members()

                st.success(f"✅ Member **{name}** added successfully!")
                st.session_state['add_member_reset'] = True
                st.rerun()

with tabs[3]:
    st.subheader("🔄 Renew or Edit Member")

    if members.empty:
        st.info("No members available. Add members first.")
    else:
        # Member selector
        member_id_sel = st.selectbox(
            "Select Member",
            options=members['MemberID'].tolist(),
            help="Choose a member to view and edit details."
        )
        sel_row = members[members['MemberID'] == member_id_sel].iloc[0]

        # --- Current info card with dynamic status ---
        st.markdown("### 📋 Current Information")
        today = date.today()
        end_date_val = sel_row['EndDate'] if pd.notna(sel_row['EndDate']) else None

        if end_date_val:
            if end_date_val < today:
                status_flag = "🔴 Expired"
            elif end_date_val <= today + timedelta(days=30):
                status_flag = "🟠 Expiring Soon"
            else:
                status_flag = "🟢 Active"
        else:
            status_flag = "❓ Unknown"

        member_display = sel_row[['MemberID', 'Name', 'Email', 'Phone', 'StartDate',
                                  'EndDate', 'PlanType', 'Notes']].to_frame().T
        member_display['Status'] = status_flag
        st.dataframe(member_display, use_container_width=True)

        st.divider()

        # --- Edit form ---
        with st.form("edit_member_form"):
            st.markdown("### ✏️ Edit Details")

            col1, col2 = st.columns(2)

            with col1:
                name = st.text_input("Full Name", value=sel_row['Name'])
                email = st.text_input("Email", value=sel_row['Email'])
                phone = st.text_input("Phone", value=sel_row['Phone'])
                start_date = sel_row['StartDate'] if pd.notna(sel_row['StartDate']) else date.today()
                st.date_input("Start Date", value=start_date, disabled=True,
                              help="Original start date (cannot be changed).")

            with col2:
                plan_choice = st.selectbox(
                    "Plan Type",
                    options=list(plans.keys()),
                    index=list(plans.keys()).index(sel_row['PlanType']) if sel_row['PlanType'] in plans else 0
                )

                # Auto-calculate End Date for new plan from today
                auto_end_date = plan_end_date(today, plan_choice, plans)
                end_date = st.date_input(
                    "End Date",
                    value=sel_row['EndDate'] if pd.notna(sel_row['EndDate']) else auto_end_date,
                    help=f"If changing plan, End Date can auto-update to today + plan duration ({plans[plan_choice]} months)."
                )

                notes = st.text_area("Notes", value=sel_row.get('Notes', ''))

            st.divider()

            # --- Quick renew ---
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

            save_btn = st.form_submit_button("💾 Save Changes")

            if save_btn:
                # Apply quick renew
                new_end = end_date
                if apply_quick and renew_months > 0:
                    base = end_date if pd.notna(end_date) else today
                    year = base.year + (base.month - 1 + renew_months) // 12
                    month = (base.month - 1 + renew_months) % 12 + 1
                    day = min(base.day, 28)
                    new_end = date(year, month, day)

                # Update in database
                update_member_in_db(
                    sel_row['MemberID'],
                    name.strip(),
                    email.strip(),
                    phone.strip(),
                    start_date,  # Keep original start date
                    new_end,
                    plan_choice,
                    notes.strip()
                )

                # Refresh members DataFrame
                members = load_members()

                st.success(f"✅ Member **{name}** updated successfully.")
                st.rerun()


# --- Settings ---
with tabs[4]:
    st.header("Settings — Plans & Durations")
    plans_df = pd.DataFrame(list(plans.items()), columns=["Plan", "DurationMonths"])
    edited = st.data_editor(plans_df, num_rows="dynamic")
    if st.button("Save Plans"):
        save_plans_to_db(edited)
        st.rerun()
