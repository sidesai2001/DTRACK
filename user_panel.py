import streamlit as st
import pandas as pd
from contextlib import contextmanager
from db import get_conn, get_columns
from utils import log_action, hash_password
from datetime import datetime, timedelta
import io, csv, json

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

def render_my_hdds_tab(user):
    """View HDDs assigned by admin to this user"""
    st.subheader("💿 My Assigned HDDs")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        status_filter = st.selectbox("Filter", ["All", "issued", "sealed"])
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            query = "SELECT * FROM hdd_records WHERE team_code=?"
            params = [user]
            
            if status_filter != "All":
                query += " AND status=?"
                params.append(status_filter)
            
            query += " ORDER BY id DESC"
            rows = c.execute(query, tuple(params)).fetchall()
    except Exception as e:
        st.error(f"❌ Database error: {e}")
        rows = []
    
    df = safe_dataframe(rows, "hdd_records")
    
    if not df.empty:
        st.caption(f"📊 Total: {len(df)} HDDs")
        st.dataframe(df, use_container_width=True, height=400)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total", len(df))
        with col2:
            issued = len(df[df['status'] == 'issued']) if 'status' in df.columns else 0
            st.metric("Issued", issued)
        with col3:
            sealed = len(df[df['status'] == 'sealed']) if 'status' in df.columns else 0
            st.metric("Sealed", sealed)
    else:
        st.info("🔭 No HDDs assigned yet")

def render_assign_to_subuser_tab(user):
    """User assigns HDD to subuser"""
    st.subheader("📤 Assign HDD to Subuser")
    
    with st.form("assign_subuser_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # Get user's HDDs with issued status
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    hdds = c.execute("""
                        SELECT serial_no, unit_space FROM hdd_records 
                        WHERE team_code=? AND status='issued'
                    """, (user,)).fetchall()
                    hdd_list = [f"{h['serial_no']} - {h['unit_space']}" for h in hdds]
            except:
                hdd_list = []
            
            selected_hdd = st.selectbox("Select HDD", hdd_list if hdd_list else [""])
        
        with col2:
            # Get subusers under this user
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    subusers = c.execute("""
                        SELECT username FROM users 
                        WHERE role='subuser' AND parent_user=?
                    """, (user,)).fetchall()
                    subuser_list = [s['username'] for s in subusers]
            except:
                subuser_list = []
            
            subuser = st.selectbox("Assign to Subuser", subuser_list if subuser_list else [""])
        
        notes = st.text_area("Assignment Notes", placeholder="Instructions for subuser...")
        
        if st.form_submit_button("📤 Assign to Subuser", use_container_width=True):
            if not selected_hdd or not subuser:
                st.error("⚠️ Select HDD and Subuser")
            else:
                try:
                    serial_no = selected_hdd.split(" - ")[0]
                    with db_connection() as conn:
                        c = conn.cursor()
                        now = datetime.utcnow().isoformat()
                        update_note = f"\n[ASSIGNED TO SUBUSER {now} by {user} to {subuser}]: {notes}"
                        c.execute("""
                            UPDATE hdd_records 
                            SET assigned_subuser=?, data_details=COALESCE(data_details, '') || ?
                            WHERE serial_no=? AND team_code=?
                        """, (subuser, update_note, serial_no, user))
                        conn.commit()
                    st.success(f"✅ HDD {serial_no} assigned to {subuser}")
                    log_action(user, f"assign_subuser:{serial_no}:{subuser}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")

def render_mark_sealed_tab(user):
    """User marks HDD as sealed when received from subuser"""
    st.subheader("🔒 Mark HDD as Sealed")
    
    st.info("ℹ️ Mark HDD as sealed when data entry is complete and received from subuser")
    
    # Get HDDs that can be sealed (issued status)
    try:
        with db_connection() as conn:
            c = conn.cursor()
            hdds = c.execute("""
                SELECT serial_no, unit_space, assigned_subuser FROM hdd_records 
                WHERE team_code=? AND status='issued'
            """, (user,)).fetchall()
            hdd_list = [f"{h['serial_no']} - {h['unit_space']} (assigned to: {h['assigned_subuser'] or 'none'})" for h in hdds]
    except:
        hdd_list = []
    
    if not hdd_list:
        st.warning("⚠️ No HDDs available to seal")
        return
    
    with st.form("seal_hdd_form", clear_on_submit=True):
        selected_hdd = st.selectbox("Select HDD", hdd_list)
        seal_notes = st.text_area("Sealing Notes", placeholder="Confirm data entry complete, ready for extraction...")
        
        if st.form_submit_button("🔒 Mark as Sealed", use_container_width=True):
            if not selected_hdd:
                st.error("⚠️ Select an HDD")
            else:
                try:
                    serial_no = selected_hdd.split(" - ")[0]
                    
                    with db_connection() as conn:
                        c = conn.cursor()
                        now = datetime.utcnow().isoformat()
                        seal_note = f"\n[SEALED {now} by {user}]: {seal_notes}"
                        
                        c.execute("""
                            UPDATE hdd_records 
                            SET status='sealed', data_details=COALESCE(data_details, '') || ?
                            WHERE serial_no=? AND team_code=?
                        """, (seal_note, serial_no, user))
                        conn.commit()
                    
                    st.success(f"✅ HDD {serial_no} marked as sealed")
                    log_action(user, f"seal_hdd:{serial_no}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")

def render_view_data_tab(user):
    """User views data entered by subusers (read-only)"""
    st.subheader("👁️ View Data Entered by Subusers")
    
    st.info("ℹ️ Read-only view. Only Admin can edit data.")
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            rows = c.execute("""
                SELECT serial_no, unit_space, assigned_subuser, premise_name, 
                       date_search, date_seized, data_details, status 
                FROM hdd_records 
                WHERE team_code=?
                ORDER BY id DESC
            """, (user,)).fetchall()
    except Exception as e:
        st.error(f"❌ Database error: {e}")
        rows = []
    
    df = safe_dataframe(rows, "hdd_records")
    
    if not df.empty:
        st.caption(f"📊 Total: {len(df)} records")
        
        # Filter by subuser
        subusers = df['assigned_subuser'].unique() if 'assigned_subuser' in df.columns else []
        selected_subuser = st.selectbox("Filter by Subuser", ["All"] + [s for s in subusers if s])
        
        if selected_subuser != "All":
            df = df[df['assigned_subuser'] == selected_subuser]
        
        st.dataframe(df, use_container_width=True, height=400)
        
        # Show detailed view
        if not df.empty:
            st.markdown("---")
            st.markdown("##### Detailed View")
            serial_nos = df['serial_no'].tolist()
            selected = st.selectbox("Select HDD for details", serial_nos)
            
            if selected:
                detail = df[df['serial_no'] == selected].iloc[0]
                col1, col2 = st.columns(2)
                
                with col1:
                    st.text_input("Serial No", value=str(detail['serial_no']), disabled=True)
                    st.text_input("Premise", value=str(detail['premise_name'] or ''), disabled=True)
                    st.text_input("Search Date", value=str(detail['date_search'] or ''), disabled=True)
                
                with col2:
                    st.text_input("Status", value=str(detail['status']), disabled=True)
                    st.text_input("Assigned to", value=str(detail['assigned_subuser'] or ''), disabled=True)
                    st.text_input("Seized Date", value=str(detail['date_seized'] or ''), disabled=True)
                
                st.text_area("Data Details", value=str(detail['data_details'] or ''), height=200, disabled=True)
    else:
        st.info("🔭 No records found")

def render_create_subuser_tab(user):
    """User creates subusers (7-day expiry)"""
    st.subheader("👤 Create Subuser")
    
    st.info("ℹ️ Create temporary subusers for data entry. Auto-expires in 7 days.")
    
    # Show existing subusers
    try:
        with db_connection() as conn:
            c = conn.cursor()
            subusers = c.execute("""
                SELECT username, valid_till FROM users 
                WHERE role='subuser' AND parent_user=?
                ORDER BY id DESC
            """, (user,)).fetchall()
    except:
        subusers = []
    
    if subusers:
        st.markdown("##### My Subusers")
        df = safe_dataframe(subusers, "users")
        st.dataframe(df, use_container_width=True, height=200)
    
    st.markdown("##### ➕ Create New Subuser")
    with st.form("create_subuser", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            subuser_name = st.text_input("Subuser Username", placeholder="e.g., MSD-1")
            password = st.text_input("Password", type="password")
        
        with col2:
            st.caption("⏰ Auto-expires in 7 days")
            member_name = st.text_input("Team Member Name (optional)")
        
        if st.form_submit_button("Create Subuser", use_container_width=True):
            if not subuser_name or not password:
                st.error("⚠️ Provide username and password")
            elif len(password) < 6:
                st.error("⚠️ Password must be 6+ characters")
            else:
                try:
                    with db_connection() as conn:
                        c = conn.cursor()
                        valid_till = (datetime.utcnow() + timedelta(days=7)).isoformat()
                        pw_hash = hash_password(password)
                        
                        c.execute("""
                            INSERT INTO users(username, password_hash, role, approved, valid_till, parent_user) 
                            VALUES (?,?,?,1,?,?)
                        """, (subuser_name, pw_hash, 'subuser', valid_till, user))
                        conn.commit()
                    
                    st.success(f"✅ Subuser {subuser_name} created (expires {valid_till[:10]})")
                    log_action(user, f"create_subuser:{subuser_name}")
                    st.rerun()
                except Exception as e:
                    if 'unique' in str(e).lower():
                        st.error("❌ Username already exists")
                    else:
                        st.error(f"❌ Error: {e}")

def render_extraction_status_tab(user):
    """View extraction and analysis status"""
    st.subheader("🔍 Extraction & Analysis Status")
    
    tab1, tab2 = st.tabs(["Extractions", "Analysis"])
    
    with tab1:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                extractions = c.execute("""
                    SELECT e.* 
                    FROM extraction_records e
                    JOIN hdd_records h ON e.original_hdd_sn = h.serial_no
                    WHERE h.team_code=?
                    ORDER BY e.id DESC
                """, (user,)).fetchall()
        except:
            extractions = []
        
        df = safe_dataframe(extractions, "extraction_records")
        if not df.empty:
            st.dataframe(df, use_container_width=True, height=300)
        else:
            st.info("📭 No extraction records")
    
    with tab2:
        try:
            with db_connection() as conn:
                c = conn.cursor()
                analysis = c.execute("""
                    SELECT a.* 
                    FROM analysis_records a
                    JOIN extraction_records e ON a.extracted_hdd_sn = e.extracted_hdd_sn
                    JOIN hdd_records h ON e.original_hdd_sn = h.serial_no
                    WHERE h.team_code=?
                    ORDER BY a.id DESC
                """, (user,)).fetchall()
        except:
            analysis = []
        
        df = safe_dataframe(analysis, "analysis_records")
        if not df.empty:
            st.dataframe(df, use_container_width=True, height=300)
        else:
            st.info("📭 No analysis records")

def user_panel(user):
    """Main user (conducting team) panel"""
    st.header("👤 User Panel (Conducting Team)")
    st.caption(f"Logged in as: {user}")
    
    tabs = st.tabs([
        "💿 My HDDs", 
        "📤 Assign to Subuser",
        "🔒 Mark Sealed",
        "👁️ View Data",
        "👤 Create Subuser",
        "🔍 Status"
    ])
    
    with tabs[0]:
        render_my_hdds_tab(user)
    
    with tabs[1]:
        render_assign_to_subuser_tab(user)
    
    with tabs[2]:
        render_mark_sealed_tab(user)
    
    with tabs[3]:
        render_view_data_tab(user)
    
    with tabs[4]:
        render_create_subuser_tab(user)
    
    with tabs[5]:
        render_extraction_status_tab(user)