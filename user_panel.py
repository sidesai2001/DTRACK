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

# Status color mapping
STATUS_COLORS = {
    'available': {'bg': '#d4edda', 'text': '#155724'},      # Green
    'issued': {'bg': '#fff3cd', 'text': '#856404'},          # Yellow/Amber
    'sealed': {'bg': '#cce5ff', 'text': '#004085'},          # Blue
    'returned': {'bg': '#e2e3e5', 'text': '#383d41'},        # Gray
    'in_extraction': {'bg': '#f8d7da', 'text': '#721c24'},   # Red/Pink
}

# Assignment color mapping (overlay on status colors)
ASSIGNMENT_COLORS = {
    'user_only': {'bg': '#e8f5e9', 'text': '#2e7d32', 'border': '#4caf50'},      # Light green - assigned to user only
    'subuser': {'bg': '#fff9c4', 'text': '#f57f17', 'border': '#fbc02d'},        # Light yellow - assigned to subuser
    'sealed_user': {'bg': '#bbdefb', 'text': '#1565c0', 'border': '#2196f3'},    # Light blue - sealed, user level
    'sealed_subuser': {'bg': '#c5cae9', 'text': '#283593', 'border': '#3f51b5'}, # Light indigo - sealed, subuser level
}

def style_status_dataframe(df):
    """Apply color styling to dataframe based on status and assignment"""
    if df.empty or 'status' not in df.columns:
        return df

    def highlight_row(row):
        status = row.get('status', '')
        assigned_subuser = row.get('assigned_subuser', None)

        # Determine color based on status and assignment
        if status == 'issued':
            if assigned_subuser and assigned_subuser.strip():
                # Issued to subuser - bright yellow/amber
                colors = {'bg': '#fff3cd', 'text': '#856404', 'border': '#ffc107'}
            else:
                # Issued to user only - light amber
                colors = {'bg': '#fff8e1', 'text': '#f57f17', 'border': '#ffb300'}
        elif status == 'sealed':
            if assigned_subuser and assigned_subuser.strip():
                # Sealed with subuser - deep blue
                colors = {'bg': '#bbdefb', 'text': '#0d47a1', 'border': '#1976d2'}
            else:
                # Sealed user only - light blue
                colors = {'bg': '#e3f2fd', 'text': '#1565c0', 'border': '#42a5f5'}
        else:
            # Other statuses use default colors
            colors = STATUS_COLORS.get(status, {'bg': 'white', 'text': 'black', 'border': '#ddd'})
            if 'border' not in colors:
                colors['border'] = '#ddd'

        # Add border for assigned subusers
        border_style = f"3px solid {colors.get('border', '#ddd')}" if assigned_subuser and assigned_subuser.strip() else ""

        return [f"background-color: {colors['bg']}; color: {colors['text']}; border-left: {border_style}; font-weight: {'600' if assigned_subuser and assigned_subuser.strip() else '400'}" for _ in row]

    styled = df.style.apply(highlight_row, axis=1)
    return styled

def render_status_legend():
    """Render status color legend with assignment indicators"""
    st.markdown("""
    <div style="margin-bottom: 15px;">
        <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; padding: 10px; background: #f8f9fa; border-radius: 8px;">
            <div style="font-weight: 600; color: #333; width: 100%; margin-bottom: 5px;">Status Colors:</div>
            <span style="padding: 4px 10px; background: #d4edda; color: #155724; border-radius: 4px; font-size: 11px;">🟢 Available</span>
            <span style="padding: 4px 10px; background: #fff8e1; color: #f57f17; border-radius: 4px; font-size: 11px;">🟡 Issued (User Only)</span>
            <span style="padding: 4px 10px; background: #fff3cd; color: #856404; border-radius: 4px; font-size: 11px; border-left: 3px solid #ffc107; font-weight: 600;">🟠 Issued (Subuser)</span>
            <span style="padding: 4px 10px; background: #e3f2fd; color: #1565c0; border-radius: 4px; font-size: 11px;">🔵 Sealed (User Only)</span>
            <span style="padding: 4px 10px; background: #bbdefb; color: #0d47a1; border-radius: 4px; font-size: 11px; border-left: 3px solid #1976d2; font-weight: 600;">🔷 Sealed (Subuser)</span>
            <span style="padding: 4px 10px; background: #e2e3e5; color: #383d41; border-radius: 4px; font-size: 11px;">⚪ Returned</span>
            <span style="padding: 4px 10px; background: #f8d7da; color: #721c24; border-radius: 4px; font-size: 11px;">🔴 In Extraction</span>
        </div>
        <div style="padding: 8px 10px; background: #e8f4f8; border-radius: 6px; font-size: 11px; color: #0277bd;">
            <strong>💡 Tip:</strong> Rows with <strong>thick colored left border</strong> and <strong>bold text</strong> indicate HDDs assigned to subusers
        </div>
    </div>
    """, unsafe_allow_html=True)
def get_subusers_with_hdd(parent_user):
    """Get set of subuser usernames that have HDDs assigned"""
    try:
        with db_connection() as conn:
            c = conn.cursor()
            assigned = c.execute("""
                SELECT DISTINCT assigned_subuser FROM hdd_records 
                WHERE team_code=? AND assigned_subuser IS NOT NULL AND assigned_subuser != ''
            """, (parent_user,)).fetchall()
            return {a['assigned_subuser'] for a in assigned}
    except:
        return set()

def format_subuser_list_with_hdd_status(subusers, parent_user):
    """Format subuser list with color indicators for HDD assignment status"""
    subusers_with_hdd = get_subusers_with_hdd(parent_user)
    
    formatted_list = []
    for s in subusers:
        uname = s['username']
        if uname in subusers_with_hdd:
            formatted_list.append(f"🔴 {uname} (has HDD)")
        else:
            formatted_list.append(f"🟢 {uname}")
    
    return formatted_list

def extract_username_from_selection(selection):
    """Extract actual username from formatted selection string"""
    if not selection or selection == "":
        return None
    # Remove emoji and status indicator
    if selection.startswith("🔴 ") or selection.startswith("🟢 "):
        uname = selection[2:].strip()  # Remove emoji
        if " (has HDD)" in uname:
            uname = uname.replace(" (has HDD)", "")
        return uname
    return selection

def render_my_hdds_tab(user):
    """View HDDs assigned by admin to this user"""
    st.subheader("💿 My Assigned HDDs")
    # Status legend
    render_status_legend()
    
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
        # Status metrics
        col1, col2, col3, col4 = st.columns(4)

        # Calculate assignments
        assigned_to_subuser = len(df[(df['assigned_subuser'].notna()) & (df['assigned_subuser'] != '')]) if 'assigned_subuser' in df.columns else 0

        with col1:
            st.metric("📊 Total HDDs", len(df))
        with col2:
            issued = len(df[df['status'] == 'issued']) if 'status' in df.columns else 0
            st.metric("🟡 Issued", issued)
        with col3:
            sealed = len(df[df['status'] == 'sealed']) if 'status' in df.columns else 0
            st.metric("🔵 Sealed", sealed)
        with col4:
            st.metric("👥 With Subuser", assigned_to_subuser)

        # Color-coded dataframe
        styled_df = style_status_dataframe(df)
        st.dataframe(styled_df, use_container_width=True, height=400)
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
            # Get subusers under this user with HDD status
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    subusers = c.execute("""
                        SELECT username FROM users 
                        WHERE role='subuser' AND parent_user=?
                    """, (user,)).fetchall()
                    subuser_list = format_subuser_list_with_hdd_status(subusers, user)
            except:
                subuser_list = []
            
            subuser_selection = st.selectbox("Assign to Subuser", subuser_list if subuser_list else [""])
            st.caption("🟢 = Available | 🔴 = Already has HDD")
        
        notes = st.text_area("Assignment Notes", placeholder="Instructions for subuser...")
        
        if st.form_submit_button("📤 Assign to Subuser", use_container_width=True):
            subuser = extract_username_from_selection(subuser_selection)
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
    
    # Status legend
    render_status_legend()
    
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
        # Status metrics
        col1, col2, col3, col4 = st.columns(4)
        status_counts = df['status'].value_counts().to_dict() if 'status' in df.columns else {}
        
        with col1:
            st.metric("📊 Total", len(df))
        with col2:
            st.metric("🟡 Issued", status_counts.get('issued', 0))
        with col3:
            st.metric("🔵 Sealed", status_counts.get('sealed', 0))
        with col4:
            st.metric("🔴 In Extraction", status_counts.get('in_extraction', 0))
        
        # Filter by subuser
        subusers = df['assigned_subuser'].unique() if 'assigned_subuser' in df.columns else []
        selected_subuser = st.selectbox("Filter by Subuser", ["All"] + [s for s in subusers if s])
        
        filtered_df = df.copy()
        if selected_subuser != "All":
            filtered_df = df[df['assigned_subuser'] == selected_subuser]
        
        # Color-coded dataframe
        styled_df = style_status_dataframe(filtered_df)
        st.dataframe(styled_df, use_container_width=True, height=400)
        
        # Show detailed view
        if not filtered_df.empty:
            st.markdown("---")
            st.markdown("##### 📄 Detailed View")
            serial_nos = filtered_df['serial_no'].tolist()
            selected = st.selectbox("Select HDD for details", serial_nos)
            
            if selected:
                detail = filtered_df[filtered_df['serial_no'] == selected].iloc[0]
                
                # Status badge
                status = detail['status']
                status_color = STATUS_COLORS.get(status, {'bg': '#e2e3e5', 'text': '#383d41'})
                st.markdown(f"""
                <span style="padding: 6px 12px; background: {status_color['bg']}; color: {status_color['text']}; 
                      border-radius: 6px; font-weight: 600; display: inline-block; margin-bottom: 15px;">
                    Status: {status.upper()}
                </span>
                """, unsafe_allow_html=True)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.text_input("Serial No", value=str(detail['serial_no']), disabled=True)
                    st.text_input("Premise", value=str(detail['premise_name'] or ''), disabled=True)
                    st.text_input("Search Date", value=str(detail['date_search'] or ''), disabled=True)
                
                with col2:
                    st.text_input("Unit Space", value=str(detail['unit_space'] or ''), disabled=True)
                    st.text_input("Assigned to", value=str(detail['assigned_subuser'] or ''), disabled=True)
                    st.text_input("Seized Date", value=str(detail['date_seized'] or ''), disabled=True)
                
                st.text_area("Data Details", value=str(detail['data_details'] or ''), height=200, disabled=True)
    else:
        st.info("🔭 No records found")

def render_create_subuser_tab(user):
    """User creates subusers (7-day expiry)"""
    st.subheader("👤 Create Subuser")
    
    st.info("ℹ️ Create temporary subusers for data entry. Auto-expires in 7 days.")
    
    # Show existing subusers with HDD status
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
        # Add HDD status column to dataframe
        subusers_with_hdd = get_subusers_with_hdd(user)
        df_data = []
        for s in subusers:
            has_hdd = "🔴 Yes" if s['username'] in subusers_with_hdd else "🟢 No"
            df_data.append({
                "Username": s['username'],
                "Valid Till": s['valid_till'],
                "Has HDD": has_hdd
            })
        df = pd.DataFrame(df_data)
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
    
    tab1, tab2 = st.tabs(["📤 Extractions", "📊 Analysis"])
    
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
            st.caption(f"📊 Total: {len(df)} records")
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
            st.caption(f"📊 Total: {len(df)} records")
            st.dataframe(df, use_container_width=True, height=300)
        else:
            st.info("📭 No analysis records")

def user_panel(user):
    """Main user (conducting team) panel"""
    st.header(f"👤 {user} (Conducting Team)")
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