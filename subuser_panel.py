import streamlit as st
import pandas as pd
from contextlib import contextmanager
from db import get_conn, get_columns
from utils import log_action
from datetime import datetime

@contextmanager
def db_connection():
    conn = None
    try:
        conn = get_conn()
        yield conn
    finally:
        if conn:
            conn.close()

def safe_dataframe(rows, table: str):
    try:
        if rows:
            return pd.DataFrame(rows, columns=rows[0].keys())
        cols = get_columns(table)
        return pd.DataFrame([], columns=cols)
    except Exception:
        return pd.DataFrame([])

def get_parent_user(subuser):
    """Get parent user of subuser"""
    try:
        with db_connection() as conn:
            c = conn.cursor()
            result = c.execute("SELECT parent_user FROM users WHERE username=?", (subuser,)).fetchone()
            return result['parent_user'] if result else None
    except:
        return None

def render_enter_data_tab(user):
    """Subuser enters seized data details only"""
    st.subheader("✏️ Enter Seized Data Details")
    
    parent = get_parent_user(user)
    st.info(f"ℹ️ Entering data for team: {parent}")
    
    # Get HDDs assigned to this subuser
    try:
        with db_connection() as conn:
            c = conn.cursor()
            hdds = c.execute("""
                SELECT serial_no, unit_space FROM hdd_records 
                WHERE team_code=? AND assigned_subuser=? AND status='issued'
            """, (parent, user)).fetchall()
            hdd_list = [f"{h['serial_no']} - {h['unit_space']}" for h in hdds]
    except:
        hdd_list = []
    
    if not hdd_list:
        st.warning("⚠️ No HDDs assigned to you")
        st.caption("Contact your team lead to assign HDDs")
        return
    
    with st.form("enter_data_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            selected_hdd = st.selectbox("Select HDD", hdd_list)
            premise_name = st.text_input("Premise Name", placeholder="Office of Mr. ABC")
            date_search = st.date_input("Date of Search")
        
        with col2:
            date_seized = st.date_input("Date of Device Seized")
        
        data_details = st.text_area("Data Details", 
                                   placeholder="• Email dump of xyz.com\n• WhatsApp backup from device\n• Financial Excel files\n• Device forensic images",
                                   height=200)
        
        if st.form_submit_button("💾 Save Data Details", use_container_width=True):
            if not selected_hdd or not premise_name or not data_details:
                st.error("⚠️ Fill all required fields")
            else:
                try:
                    serial_no = selected_hdd.split(" - ")[0]
                    
                    with db_connection() as conn:
                        c = conn.cursor()
                        now = datetime.utcnow().isoformat()
                        
                        # Build data entry log
                        data_entry = f"\n[DATA ENTRY {now} by {user}]:\nPremise: {premise_name}\nSearch Date: {date_search}\nSeized Date: {date_seized}\n\nData Details:\n{data_details}"
                        
                        # Update record with data
                        c.execute("""
                            UPDATE hdd_records 
                            SET premise_name=?, 
                                date_search=?, 
                                date_seized=?, 
                                data_details=COALESCE(data_details, '') || ?
                            WHERE serial_no=? AND team_code=? AND assigned_subuser=?
                        """, (premise_name, date_search.isoformat(), date_seized.isoformat(), 
                              data_entry, serial_no, parent, user))
                        conn.commit()
                    
                    st.success(f"✅ Data saved for HDD {serial_no}")
                    log_action(user, f"enter_data:{serial_no}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")

def render_my_hdds_tab(user):
    """View HDDs assigned to this subuser"""
    st.subheader("💿 My Assigned HDDs")
    
    parent = get_parent_user(user)
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            rows = c.execute("""
                SELECT serial_no, unit_space, premise_name, date_search, date_seized, status
                FROM hdd_records 
                WHERE team_code=? AND assigned_subuser=?
                ORDER BY id DESC
            """, (parent, user)).fetchall()
    except Exception as e:
        st.error(f"❌ Database error: {e}")
        rows = []
    
    df = safe_dataframe(rows, "hdd_records")
    
    if not df.empty:
        st.caption(f"📊 Total: {len(df)} HDDs")
        st.dataframe(df, use_container_width=True, height=400)
        
        # Stats
        col1, col2 = st.columns(2)
        with col1:
            with_data = len(df[df['premise_name'].notna()]) if 'premise_name' in df.columns else 0
            st.metric("With Data Entered", with_data)
        with col2:
            pending = len(df[df['premise_name'].isna()]) if 'premise_name' in df.columns else 0
            st.metric("Pending Data Entry", pending)
    else:
        st.info("🔭 No HDDs assigned to you")

def render_account_tab(user):
    """Display subuser account info"""
    st.subheader("👤 Account Information")
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            info = c.execute("""
                SELECT username, role, valid_till, parent_user 
                FROM users WHERE username=?
            """, (user,)).fetchone()
    except:
        info = None
    
    if info:
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Username", info['username'])
            st.metric("Parent Team", info['parent_user'] or "N/A")
        
        with col2:
            if info['valid_till']:
                valid_date = datetime.fromisoformat(info['valid_till'])
                days_left = (valid_date - datetime.utcnow()).days
                
                if days_left <= 0:
                    st.metric("Status", "EXPIRED", delta="Account expired")
                    st.error("⚠️ Your account has expired. Contact your team lead.")
                elif days_left <= 2:
                    st.metric("Expires In", f"{days_left} days", delta=f"{valid_date.strftime('%Y-%m-%d')}")
                    st.warning(f"⚠️ Account expires in {days_left} day(s)")
                else:
                    st.metric("Expires In", f"{days_left} days", delta=f"{valid_date.strftime('%Y-%m-%d')}")
            else:
                st.metric("Expires", "Never")
        
        st.info("ℹ️ Your role: Data entry only. Contact team lead for issues.")
    else:
        st.error("❌ Account information not found")

def subuser_panel(user):
    """Main subuser panel - data entry only"""
    st.header("🧑‍💻 Subuser Panel (Data Entry)")
    st.caption(f"Logged in as: {user}")
    
    # Check account validity
    try:
        with db_connection() as conn:
            c = conn.cursor()
            info = c.execute("SELECT valid_till FROM users WHERE username=?", (user,)).fetchone()
            
            if info and info['valid_till']:
                valid_date = datetime.fromisoformat(info['valid_till'])
                if valid_date < datetime.utcnow():
                    st.error("⚠️ Your account has expired. Contact your team lead.")
                    st.stop()
                
                days_left = (valid_date - datetime.utcnow()).days
                if days_left <= 2:
                    st.warning(f"⚠️ Account expires in {days_left} day(s)")
    except:
        pass
    
    tabs = st.tabs(["✏️ Enter Data", "💿 My HDDs", "👤 Account"])
    
    with tabs[0]:
        render_enter_data_tab(user)
    
    with tabs[1]:
        render_my_hdds_tab(user)
    
    with tabs[2]:
        render_account_tab(user)