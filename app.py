import streamlit as st
import pandas as pd
from contextlib import contextmanager
from datetime import datetime, timedelta
from db import init_db, get_conn
from utils import (check_password, hash_password, get_user, log_action, 
                   create_user, ensure_default_admin)
import admin, user_panel, subuser_panel
from PIL import Image

def fix_selectbox_color():
    st.markdown("""
        <style>

        /* Fix selected text inside the selectbox */
        div[data-baseweb="select"] > div {
            color: black !important;
        }

        /* Fix dropdown menu text */
        div[data-baseweb="menu"] div {
            color: black !important;
        }

        /* Fix placeholder text */
        div[data-baseweb="select"] span {
            color: black !important;
        }

        /* Fix selected item highlight */
        div[data-baseweb="select"] [aria-selected="true"] {
            background-color: #dce6ff !important;
            color: black !important;
        }

        /* Control itself (the box) */
        div[data-baseweb="select"] {
            background-color: white !important;
            color: black !important;
        }

        /* Fix arrow icon visibility */
        div[data-baseweb="select"] svg {
            fill: black !important;
        }

        </style>
    """, unsafe_allow_html=True)

# Page config
st.set_page_config(
    page_title='DIAL - Digital Intelligence & Analytics Lab',
    page_icon='💽',
    layout='wide',
    initial_sidebar_state='expanded'
)

# Initialize
init_db()
ensure_default_admin()
fix_selectbox_color()
# Enhanced CSS


# Header
logo = Image.open('assets/logo.jpg')
st.image(logo, width=450)
# st.caption("DIAL - Digital Intelligence & Analytics Lab")

# Initialize session state
def init_session_state():
    """Initialize session state variables"""
    defaults = {
        'logged_in': False,
        'user': None,
        'role': None,
        'serial_no': ''
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()


@contextmanager
def db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        conn = get_conn()
        yield conn
    except Exception as e:
        st.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def render_login():
    """Render login form"""
    st.header('🔐 Login')
    with st.form('login', clear_on_submit=False):
        uname = st.text_input('Username', placeholder='Enter your username')
        pwd = st.text_input('Password', type='password', placeholder='Enter your password')
        col1, col2 = st.columns([1, 3])
        with col1:
            submit = st.form_submit_button('Login', use_container_width=True)
        
        if submit:
            if not uname or not pwd:
                st.error('⚠️ Please enter both username and password.')
                return
            
            try:
                with db_connection() as conn:
                    c = conn.cursor()
                    row = c.execute('SELECT * FROM users WHERE username=?', (uname,)).fetchone()
                    
                    if not row:
                        st.error('❌ User not found.')
                        log_action(uname, 'login_failed_no_user')
                        return
                    
                    if row['approved'] == 0:
                        st.warning('⏳ Your account is pending admin approval.')
                        return
                    
                    if not check_password(pwd, row['password_hash']):
                        st.error('❌ Invalid password.')
                        log_action(uname, 'login_failed_wrong_password')
                        return
                    
                    # Check password expiry
                    if row['password_expiry']:
                        try:
                            if datetime.fromisoformat(row['password_expiry']) < datetime.utcnow():
                                st.warning('🔑 Your password has expired. Contact admin to reset.')
                                return
                        except Exception:
                            pass
                    
                    # Check subuser validity
                    if row['role'] == 'subuser' and row['valid_till']:
                        try:
                            if datetime.fromisoformat(row['valid_till']) < datetime.utcnow():
                                st.error('⏰ Sub-user account has expired.')
                                return
                        except Exception:
                            st.error('⚠️ Invalid account validity. Contact admin.')
                            return
                    
                    # Successful login
                    st.session_state.logged_in = True
                    st.session_state.user = uname
                    st.session_state.role = row['role']
                    log_action(uname, 'login_success')
                    st.success('✅ Login successful!')
                    st.rerun()
                    
            except Exception as e:
                st.error(f'❌ Login error: {e}')


def render_register():
    """Render registration form"""
    st.header('📝 Register - Conducting Team')
    st.info('ℹ️ Register your team account. Admin approval required before you can login.')
    
    with st.form('reg', clear_on_submit=True):
        uname = st.text_input('Team Code / Username', placeholder='Enter unique team code')
        pwd = st.text_input('Password', type='password', placeholder='Enter secure password')
        pwd_confirm = st.text_input('Confirm Password', type='password', placeholder='Re-enter password')
        
        col1, col2 = st.columns([1, 3])
        with col1:
            submit = st.form_submit_button('Register', use_container_width=True)
        
        if submit:
            if not uname or not pwd:
                st.error('⚠️ Please provide username and password.')
                return
            
            if pwd != pwd_confirm:
                st.error('⚠️ Passwords do not match.')
                return
            
            if len(pwd) < 6:
                st.error('⚠️ Password must be at least 6 characters long.')
                return
            
            try:
                create_user(uname, pwd, role='user', approved=0)
                st.success('✅ Registration successful! Await admin approval to login.')
                log_action(uname, 'registered')
            except Exception as e:
                error_msg = str(e).lower()
                if 'unique' in error_msg or 'already exists' in error_msg:
                    st.error('❌ Username already taken. Please choose another.')
                else:
                    st.error(f'❌ Registration failed: {e}')


# def render_quick_hdd():
#     """Render quick HDD add form"""
#     st.markdown('---')
#     st.subheader('⚡ Quick HDD Add / Search')
    
#     # Scanner integration
#     try:
#         from scanner import scan_block
#         scan_result = scan_block()
#         if scan_result:
#             st.success(f"📷 Scanned: {scan_result}")
#             st.session_state['serial_no'] = scan_result
#     except ImportError:
#         pass  # Scanner module optional
#     except Exception as e:
#         st.info(f"ℹ️ Scanner not available: {e}")
    
#     with st.expander('➕ Add HDD Record', expanded=False):
#         with st.form('quick_hdd', clear_on_submit=True):
#             col1, col2 = st.columns(2)
            
#             with col1:
#                 s_no = st.text_input(
#                     'Serial No *', 
#                     value=st.session_state.get('serial_no', ''),
#                     placeholder='Enter or scan serial number'
#                 )
#                 space = st.selectbox('Unit Space *', ['1TB', '2TB', '4TB', '8TB', '16TB'])
#                 tcode = st.text_input(
#                     'Team Code *', 
#                     value=st.session_state.user if st.session_state.role == 'user' else '',
#                     placeholder='Team identifier'
#                 )
#                 prem = st.text_input('Premise Name *', placeholder='Location of seizure')
            
#             with col2:
#                 dsearch = st.date_input('Date of Search', value=datetime.now())
#                 dseized = st.date_input('Date of Device Seized', value=datetime.now())
#                 status = st.selectbox('Status', ['available', 'sealed', 'issued', 'returned'])
#                 details = st.text_area('Data Details', placeholder='Brief description of data...')
            
#             col1, col2 = st.columns([1, 4])
#             with col1:
#                 submit = st.form_submit_button('💾 Save', use_container_width=True)
            
#             if submit:
#                 if not s_no or not tcode or not prem:
#                     st.error('⚠️ Serial No, Team Code, and Premise are required.')
#                     return
                
#                 try:
#                     with db_connection() as conn:
#                         c = conn.cursor()
#                         now = datetime.utcnow().isoformat()
#                         c.execute('''
#                             INSERT INTO hdd_records 
#                             (serial_no, unit_space, team_code, premise_name, 
#                              date_search, date_seized, data_details, created_by, 
#                              created_on, barcode_value, status) 
#                             VALUES (?,?,?,?,?,?,?,?,?,?,?)
#                         ''', (s_no, space, tcode, prem, dsearch.isoformat(), 
#                               dseized.isoformat(), details, st.session_state.user, 
#                               now, s_no, status))
#                         conn.commit()
#                         st.success(f'✅ HDD record {s_no} saved successfully!')
#                         log_action(st.session_state.user, f'quick_add:{s_no}')
#                         st.session_state['serial_no'] = ''  # Clear scanned value
#                 except Exception as e:
#                     if 'unique' in str(e).lower():
#                         st.error(f'❌ Serial number {s_no} already exists.')
#                     else:
#                         st.error(f'❌ Failed to save: {e}')


def main():
    """Main application logic"""
    try:
        if not st.session_state.logged_in:
            # Sidebar for unauthenticated users
            st.sidebar.title('Welcome to DTRACK')
            action = st.sidebar.radio(
                'Choose Action',
                ['Login', 'Register', 'About'],
                label_visibility='visible'
            )
            
            if action == 'About':
                st.sidebar.markdown('---')
                st.sidebar.info('''
                **DTRACK** is a prototype system for tracking digital evidence.
                
                - Register as a conducting team
                - Admin approves registrations
                - Manage HDD records efficiently
                ''')
                
                st.info('''
                ### 📖 About DTRACK
                
                DTRACK is a digital evidence tracking system designed for law enforcement 
                and investigation teams. It provides:
                
                - **Secure Access Control**: Role-based authentication
                - **HDD Management**: Track and manage digital storage devices
                - **Audit Trail**: Complete logging of all actions
                - **Team Collaboration**: Support for multiple teams and sub-users
                
                Contact your administrator for access.
                ''')
            
            elif action == 'Register':
                render_register()
            
            elif action == 'Login':
                render_login()
        
        else:
            # Logged in users
            st.sidebar.success(f"👤 {st.session_state.user}")
            st.sidebar.caption(f"Role: {st.session_state.role.upper()}")
            
            if st.sidebar.button('🚪 Logout', use_container_width=True):
                log_action(st.session_state.user, 'logout')
                for key in ['logged_in', 'user', 'role']:
                    st.session_state[key] = None if key != 'logged_in' else False
                st.rerun()
            
            # Route to appropriate panel
            role = st.session_state.role
            user = st.session_state.user
            
            if role == 'admin':
                admin.admin_panel(user)
            elif role == 'user':
                user_panel.user_panel(user)
            elif role == 'subuser':
                subuser_panel.subuser_panel(user)
            
            # Quick HDD form for all logged-in users
            # render_quick_hdd()
            
            st.info('💡 Use the role-specific panels above for full features.')
    
    except Exception as e:
        st.error(f'❌ Unexpected error: {e}')
        if st.button('🔄 Reload Application'):
            st.rerun()


if __name__ == '__main__':
    main()