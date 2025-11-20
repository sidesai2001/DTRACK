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

def render_add_hdd_tab(user):
    """Admin adds HDD to system (only admin can do this)"""
    st.subheader("💿 Add New HDD")
    
    with st.form("add_hdd_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            serial_no = st.text_input("Serial No", placeholder="Scan or enter S.N.")
            unit = st.text_input("Unit", value="4(1) Delhi")
            hd_space = st.selectbox("HD Space", ["1TB", "2TB SSD", "4TB", "8TB"])
        
        with col2:
            status = st.selectbox("Initial Status", ["available", "sealed"])
            notes = st.text_area("Notes", placeholder="Initial notes...")
        
        if st.form_submit_button("💾 Add HDD", use_container_width=True):
            if not serial_no:
                st.error("⚠️ Serial No required")
            else:
                try:
                    with db_connection() as conn:
                        c = conn.cursor()
                        now = datetime.utcnow().isoformat()
                        c.execute("""
                            INSERT INTO hdd_records 
                            (serial_no, unit, unit_space, status, created_by, created_on, barcode_value, data_details)
                            VALUES (?,?,?,?,?,?,?,?)
                        """, (serial_no, unit, hd_space, status, user, now, serial_no, notes))
                        conn.commit()
                    st.success(f"✅ HDD {serial_no} added to system")
                    log_action(user, f"add_hdd:{serial_no}")
                    st.rerun()
                except Exception as e:
                    if 'unique' in str(e).lower():
                        st.error("❌ Serial No already exists")
                    else:
                        st.error(f"❌ Error: {e}")

def render_assign_hdd_tab(user):
    """Admin assigns HDD to conducting team (User)"""
    st.subheader("📤 Assign HDD to User")
    
    with st.form("assign_hdd_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # Get available HDDs
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    hdds = c.execute("""
                        SELECT serial_no, unit_space FROM hdd_records 
                        WHERE team_code IS NULL OR team_code = ''
                    """).fetchall()
                    hdd_list = [f"{h['serial_no']} - {h['unit_space']}" for h in hdds]
            except:
                hdd_list = []
            
            selected_hdd = st.selectbox("Select HDD", hdd_list if hdd_list else [""])
        
        with col2:
            # Get approved users
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    users = c.execute("SELECT username FROM users WHERE role='user' AND approved=1").fetchall()
                    user_list = [u['username'] for u in users]
            except:
                user_list = []
            
            team_code = st.selectbox("Assign to User", user_list if user_list else [""])
        
        notes = st.text_area("Assignment Notes", placeholder="Assignment details...")
        
        if st.form_submit_button("📤 Assign HDD", use_container_width=True):
            if not selected_hdd or not team_code:
                st.error("⚠️ Select HDD and User")
            else:
                try:
                    serial_no = selected_hdd.split(" - ")[0]
                    with db_connection() as conn:
                        c = conn.cursor()
                        now = datetime.utcnow().isoformat()
                        update_note = f"\n[ASSIGNED {now} by Admin to {team_code}]: {notes}"
                        c.execute("""
                            UPDATE hdd_records 
                            SET team_code=?, status='issued', data_details=COALESCE(data_details, '') || ?
                            WHERE serial_no=?
                        """, (team_code, update_note, serial_no))
                        conn.commit()
                    st.success(f"✅ HDD {serial_no} assigned to {team_code}")
                    log_action(user, f"assign_hdd:{serial_no}:{team_code}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")

def render_extraction_tab(user):
    """Admin disburses to vendor when HDD received from user"""
    st.subheader("🔬 Extraction Management")
    
    tab1, tab2 = st.tabs(["Send to Vendor", "Extraction Records"])
    
    with tab1:
        st.markdown("##### Send HDD for Extraction (when received from User)")
        with st.form("extraction_request", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                # Get sealed HDDs (returned by users)
                try:
                    with db_connection() as conn:
                        c = conn.cursor()
                        hdds = c.execute("""
                            SELECT serial_no, team_code FROM hdd_records 
                            WHERE status='sealed'
                        """).fetchall()
                        hdd_list = [f"{h['serial_no']} ({h['team_code']})" for h in hdds]
                except:
                    hdd_list = []
                
                selected_hdd = st.selectbox("Select Sealed HDD", hdd_list if hdd_list else [""])
                extraction_vendor = st.text_input("Extraction Vendor", placeholder="e.g., Cyint")
                date_extraction_start = st.date_input("Date of Extraction Start")
            
            with col2:
                extracted_hdd_sn = st.text_input("Extracted HDD S.No.", placeholder="New HDD for extracted data")
                working_copy_sns = st.text_area("Working Copy S.Nos", placeholder="123456789\n234321\n2345432")
                date_receiving = st.date_input("Date of Receiving Extraction Copy")
            
            if st.form_submit_button("📤 Send for Extraction", use_container_width=True):
                if not selected_hdd or not extraction_vendor:
                    st.error("⚠️ Fill required fields")
                else:
                    try:
                        original_sn = selected_hdd.split(" (")[0]
                        working_copies = [s.strip() for s in working_copy_sns.split('\n') if s.strip()]
                        
                        with db_connection() as conn:
                            c = conn.cursor()
                            orig = c.execute("SELECT * FROM hdd_records WHERE serial_no=?", (original_sn,)).fetchone()
                            
                            now = datetime.utcnow().isoformat()
                            c.execute("""
                                INSERT INTO extraction_records
                                (original_hdd_sn, unit, unit_space, team_code, data_details,
                                 date_extraction_start, extracted_hdd_sn, extracted_by, 
                                 working_copy_sns, date_receiving, created_by, created_on)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (original_sn, orig['unit'], orig['unit_space'], orig['team_code'],
                                  orig['data_details'], date_extraction_start.isoformat(),
                                  extracted_hdd_sn, extraction_vendor, json.dumps(working_copies),
                                  date_receiving.isoformat(), user, now))
                            
                            c.execute("UPDATE hdd_records SET status='in_extraction' WHERE serial_no=?", (original_sn,))
                            conn.commit()
                        
                        st.success(f"✅ HDD {original_sn} sent for extraction")
                        log_action(user, f"extraction_send:{original_sn}:{extraction_vendor}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
    
    with tab2:
        st.markdown("##### Extraction History")
        try:
            with db_connection() as conn:
                c = conn.cursor()
                rows = c.execute("SELECT * FROM extraction_records ORDER BY id DESC LIMIT 100").fetchall()
        except Exception as e:
            st.error(f"❌ Database error: {e}")
            rows = []
        
        df = safe_dataframe(rows, "extraction_records")
        if not df.empty:
            st.dataframe(df, use_container_width=True, height=400)
        else:
            st.info("📭 No extraction records")

def render_analysis_tab(user):
    """Admin disburses to analyst when received from vendor"""
    st.subheader("🔍 Analysis Management")
    
    with st.form("analysis_disburse", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # Get extracted HDDs (received from vendor)
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    extracts = c.execute("""
                        SELECT extracted_hdd_sn, extracted_by FROM extraction_records
                        WHERE extracted_hdd_sn IS NOT NULL
                    """).fetchall()
                    extract_list = [f"{e['extracted_hdd_sn']} (by {e['extracted_by']})" for e in extracts]
            except:
                extract_list = []
            
            selected_extract = st.selectbox("Select Extracted HDD", extract_list if extract_list else [""])
            analyst_name = st.text_input("Analyst Name", placeholder="Analyst/Team name")
        
        with col2:
            date_disburse = st.date_input("Date of Disbursement to Analyst")
            analysis_notes = st.text_area("Analysis Instructions", placeholder="Specific analysis requirements...")
        
        if st.form_submit_button("📊 Send for Analysis", use_container_width=True):
            if not selected_extract or not analyst_name:
                st.error("⚠️ Fill required fields")
            else:
                try:
                    extracted_sn = selected_extract.split(" (")[0]
                    
                    with db_connection() as conn:
                        c = conn.cursor()
                        now = datetime.utcnow().isoformat()
                        c.execute("""
                            INSERT INTO analysis_records
                            (extracted_hdd_sn, analyst_name, date_disburse, 
                             analysis_notes, created_by, created_on)
                            VALUES (?,?,?,?,?,?)
                        """, (extracted_sn, analyst_name, date_disburse.isoformat(),
                              analysis_notes, user, now))
                        conn.commit()
                    
                    st.success(f"✅ Extracted HDD {extracted_sn} sent to {analyst_name}")
                    log_action(user, f"analysis_disburse:{extracted_sn}:{analyst_name}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
    
    st.markdown("---")
    st.markdown("##### Analysis History")
    try:
        with db_connection() as conn:
            c = conn.cursor()
            rows = c.execute("SELECT * FROM analysis_records ORDER BY id DESC LIMIT 100").fetchall()
    except Exception as e:
        st.error(f"❌ Database error: {e}")
        rows = []
    
    df = safe_dataframe(rows, "analysis_records")
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=300)
    else:
        st.info("📭 No analysis records")

def render_edit_records_tab(user):
    """Admin can edit all HDD records"""
    st.subheader("✏️ Edit HDD Records")
    
    # Select HDD to edit
    try:
        with db_connection() as conn:
            c = conn.cursor()
            hdds = c.execute("SELECT serial_no, team_code, status FROM hdd_records ORDER BY id DESC LIMIT 100").fetchall()
            hdd_list = [f"{h['serial_no']} - {h['team_code'] or 'Unassigned'} ({h['status']})" for h in hdds]
    except:
        hdd_list = []
    
    selected = st.selectbox("Select HDD", hdd_list if hdd_list else [""])
    
    if selected:
        serial_no = selected.split(" - ")[0]
        
        try:
            with db_connection() as conn:
                c = conn.cursor()
                record = c.execute("SELECT * FROM hdd_records WHERE serial_no=?", (serial_no,)).fetchone()
        except:
            record = None
        
        if record:
            with st.form("edit_record_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    team_code = st.text_input("Team Code", value=record['team_code'] or "")
                    premise_name = st.text_input("Premise Name", value=record['premise_name'] or "")
                    date_search = st.text_input("Date Search", value=record['date_search'] or "")
                    date_seized = st.text_input("Date Seized", value=record['date_seized'] or "")
                
                with col2:
                    status = st.selectbox("Status", ["available", "issued", "sealed", "returned", "in_extraction"], 
                                        index=["available", "issued", "sealed", "returned", "in_extraction"].index(record['status']) if record['status'] in ["available", "issued", "sealed", "returned", "in_extraction"] else 0)
                    unit_space = st.text_input("Unit Space", value=record['unit_space'] or "")
                    unit = st.text_input("Unit", value=record['unit'] or "")
                
                data_details = st.text_area("Data Details", value=record['data_details'] or "", height=150)
                
                if st.form_submit_button("💾 Update Record", use_container_width=True):
                    try:
                        with db_connection() as conn:
                            c = conn.cursor()
                            c.execute("""
                                UPDATE hdd_records 
                                SET team_code=?, premise_name=?, date_search=?, date_seized=?,
                                    status=?, unit_space=?, unit=?, data_details=?
                                WHERE serial_no=?
                            """, (team_code, premise_name, date_search, date_seized, status, 
                                  unit_space, unit, data_details, serial_no))
                            conn.commit()
                        st.success(f"✅ Updated {serial_no}")
                        log_action(user, f"edit_record:{serial_no}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

def render_approve_users_tab(user):
    """Admin approves or disapproves users"""
    st.subheader("✅ Approve/Disapprove Users")
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            # Fetch all users except admin to approve/disapprove
            users = c.execute("SELECT username, approved FROM users WHERE role='user' ORDER BY username").fetchall()
    except Exception as e:
        st.error(f"❌ Database error: {e}")
        users = []
    
    if users:
        user_options = [f"{u['username']} - {'Approved' if u['approved'] else 'Not Approved'}" for u in users]
        selected = st.selectbox("Select User", user_options)
        
        if selected:
            selected_user = selected.split(" - ")[0]
            current_status = selected.split(" - ")[1] == "Approved"
            
            action = st.radio("Action", ["Approve", "Disapprove"], index=0 if not current_status else 1)
            
            if st.button(f"{action} User"):
                try:
                    with db_connection() as conn:
                        c = conn.cursor()
                        new_approved = 1 if action == "Approve" else 0
                        c.execute("UPDATE users SET approved=? WHERE username=?", (new_approved, selected_user))
                        conn.commit()
                    st.success(f"✅ User {selected_user} {action.lower()}d")
                    log_action(user, f"{action.lower()}_user:{selected_user}")
                    st.experimental_rerun()
                except Exception as e:
                    st.error(f"❌ Error updating user: {e}")
    else:
        st.info("No users available for approval management")

def render_users_tab(user):
    """Create and manage users"""
    st.subheader("👥 Manage Users")
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            users = c.execute("SELECT username, role, approved, valid_till FROM users ORDER BY username").fetchall()
    except Exception as e:
        st.error(f"❌ Database error: {e}")
        users = []
    
    df = safe_dataframe(users, "users")
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=250)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### ➕ Create User")
        with st.form("create_user_form", clear_on_submit=True):
            uname = st.text_input("Username")
            pwd = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["user", "admin"])
            
            if st.form_submit_button("Create", use_container_width=True):
                if not uname or not pwd:
                    st.error("⚠️ Fill all fields")
                elif len(pwd) < 6:
                    st.error("⚠️ Password must be 6+ characters")
                else:
                    try:
                        with db_connection() as conn:
                            c = conn.cursor()
                            pw_hash = hash_password(pwd)
                            expiry = (datetime.utcnow() + timedelta(days=90)).isoformat()
                            c.execute("""
                                INSERT INTO users(username, password_hash, role, approved, password_expiry) 
                                VALUES (?,?,?,1,?)
                            """, (uname, pw_hash, role, expiry))
                            conn.commit()
                        st.success(f"✅ User {uname} created")
                        log_action(user, f"create_user:{uname}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
    
    with col2:
        st.markdown("##### 🔒 Reset Password")
        with st.form("reset_pass_form", clear_on_submit=True):
            all_users = [u['username'] for u in users if u['username'] != user]
            reset_user = st.selectbox("Select user", all_users if all_users else [""])
            newp = st.text_input("New Password", type="password")
            
            if st.form_submit_button("Reset", use_container_width=True):
                if not reset_user or not newp:
                    st.error("⚠️ Fill all fields")
                elif len(newp) < 6:
                    st.error("⚠️ Password must be 6+ characters")
                else:
                    try:
                        with db_connection() as conn:
                            c = conn.cursor()
                            expiry = (datetime.utcnow() + timedelta(days=90)).isoformat()
                            c.execute("UPDATE users SET password_hash=?, password_expiry=? WHERE username=?",
                                    (hash_password(newp), expiry, reset_user))
                            conn.commit()
                        st.success(f"✅ Password reset for {reset_user}")
                        log_action(user, f"reset_password:{reset_user}")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

def render_subusers_tab(user):
    """Create subusers (7-day expiry)"""
    st.subheader("👤 Create Subuser")
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            subusers = c.execute("SELECT username, valid_till, parent_user FROM users WHERE role='subuser' ORDER BY id DESC").fetchall()
    except:
        subusers = []
    
    if subusers:
        df = safe_dataframe(subusers, "users")
        st.dataframe(df, use_container_width=True, height=200)
    
    with st.form("subuser_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # Get users for parent selection
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    users_list = c.execute("SELECT username FROM users WHERE role='user' AND approved=1").fetchall()
                    parent_users = [u['username'] for u in users_list]
            except:
                parent_users = []
            
            parent_team = st.selectbox("Parent User", parent_users if parent_users else [""])
            uname = st.text_input("Subuser Username", placeholder="e.g., MSD-1")
        
        with col2:
            pwd = st.text_input("Password", type="password")
            st.caption("⏰ Auto-expires in 7 days")
        
        if st.form_submit_button("Create Subuser", use_container_width=True):
            if not uname or not pwd or not parent_team:
                st.error("⚠️ Fill all fields")
            elif len(pwd) < 6:
                st.error("⚠️ Password must be 6+ characters")
            else:
                try:
                    with db_connection() as conn:
                        c = conn.cursor()
                        valid_till = (datetime.utcnow() + timedelta(days=7)).isoformat()
                        pw_hash = hash_password(pwd)
                        c.execute("""
                            INSERT INTO users(username, password_hash, role, approved, valid_till, parent_user) 
                            VALUES (?,?,?,1,?,?)
                        """, (uname, pw_hash, 'subuser', valid_till, parent_team))
                        conn.commit()
                    st.success(f"✅ Subuser {uname} created (expires {valid_till[:10]})")
                    log_action(user, f"create_subuser:{uname}:{parent_team}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")

def render_records_tab():
    """View all records"""
    st.subheader("💾 All HDD Records")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        search = st.text_input("🔍 Search S.No/Team")
    with col2:
        status_filter = st.selectbox("Status", ["All", "available", "sealed", "issued", "returned", "in_extraction"])
    with col3:
        sort_by = st.selectbox("Sort", ["Newest", "Oldest", "Serial"])
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            query = "SELECT * FROM hdd_records WHERE 1=1"
            params = []
            
            if search:
                query += " AND (serial_no LIKE ? OR team_code LIKE ?)"
                params.extend([f"%{search}%", f"%{search}%"])
            
            if status_filter != "All":
                query += " AND status=?"
                params.append(status_filter)
            
            query += " ORDER BY id " + ("DESC" if sort_by == "Newest" else "ASC" if sort_by == "Oldest" else "serial_no")
            rows = c.execute(query, params).fetchall()
    except Exception as e:
        st.error(f"❌ Database error: {e}")
        rows = []
    
    df = safe_dataframe(rows, "hdd_records")
    
    if not df.empty:
        st.caption(f"📊 Total: {len(df)}")
        st.dataframe(df, use_container_width=True, height=500)
    else:
        st.info("🔭 No records found")

def render_exports_tab():
    """Export records"""
    st.subheader("📥 Export Records")
    
    export_format = st.selectbox("Format", ["CSV", "JSON", "Excel"])
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            rows = c.execute("SELECT * FROM hdd_records ORDER BY id DESC").fetchall()
    except:
        rows = []
    
    if rows:
        st.info(f"ℹ️ {len(rows)} records")
        
        if st.button("📥 Prepare Download"):
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                if export_format == "CSV":
                    cols = rows[0].keys()
                    buf = io.StringIO()
                    writer = csv.writer(buf)
                    writer.writerow(cols)
                    for r in rows:
                        writer.writerow([r[k] for k in cols])
                    
                    st.download_button("⬇️ Download CSV", buf.getvalue(), 
                                     f"dtrack_{timestamp}.csv", "text/csv", use_container_width=True)
                
                elif export_format == "JSON":
                    data = [dict(r) for r in rows]
                    st.download_button("⬇️ Download JSON", json.dumps(data, indent=2),
                                     f"dtrack_{timestamp}.json", "application/json", use_container_width=True)
                
                else:
                    df = pd.DataFrame([dict(r) for r in rows])
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Records')
                    
                    st.download_button("⬇️ Download Excel", buf.getvalue(),
                                     f"dtrack_{timestamp}.xlsx", 
                                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                     use_container_width=True)
            except Exception as e:
                st.error(f"❌ Export error: {e}")
    else:
        st.warning("⚠️ No records to export")

def render_logs_tab():
    """View logs"""
    st.subheader("📋 System Logs")
    
    col1, col2 = st.columns(2)
    with col1:
        limit = st.selectbox("Show", [100, 500, 1000])
    with col2:
        user_filter = st.text_input("Filter by user")
    
    try:
        with db_connection() as conn:
            c = conn.cursor()
            query = "SELECT * FROM logs WHERE 1=1"
            params = []
            
            if user_filter:
                query += " AND username LIKE ?"
                params.append(f"%{user_filter}%")
            
            query += f" ORDER BY id DESC LIMIT {limit}"
            rows = c.execute(query, params).fetchall()
    except:
        rows = []
    
    df = safe_dataframe(rows, "logs")
    
    if not df.empty:
        st.dataframe(df, use_container_width=True, height=400)
    else:
        st.info("🔭 No logs")

def admin_panel(user):
    """Main admin panel"""
    st.header("👑 Admin Panel (DIAL)")
    st.caption(f"Logged in as: {user}")
    
    tabs = st.tabs([
        "➕ Add HDD", "📤 Assign HDD", "🔬 Extraction", "🔍 Analysis", 
        "✏️ Edit Records", "👥 Users", "👤 Subusers", "✔️ Approvals", 
        "💾 Records", "📥 Exports", "📋 Logs"
    ])
    
    with tabs[0]:
        render_add_hdd_tab(user)
    
    with tabs[1]:
        render_assign_hdd_tab(user)
    
    with tabs[2]:
        render_extraction_tab(user)
    
    with tabs[3]:
        render_analysis_tab(user)
    
    with tabs[4]:
        render_edit_records_tab(user)
    
    with tabs[5]:
        render_users_tab(user)
    
    with tabs[6]:
        render_subusers_tab(user)
    
    with tabs[7]:
        render_approve_users_tab(user)
    
    with tabs[8]:
        render_records_tab()
    
    with tabs[9]:
        render_exports_tab()
    
    with tabs[10]:
        render_logs_tab()