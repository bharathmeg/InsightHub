import streamlit as st
import sqlite3
import pandas as pd
import smtplib
import random
from datetime import datetime

# ---------------- DATABASE SETUP ----------------
conn = sqlite3.connect("sales_dashboard.db", check_same_thread=False)
c = conn.cursor()

# Users table
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    password TEXT,
    role TEXT,
    company TEXT,
    otp TEXT,
    UNIQUE(email, role, company)
)
''')

# Sales table
c.execute('''
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    product TEXT,
    revenue REAL,
    quantity INTEGER,
    timestamp TEXT
)
''')

# History table for undo
c.execute('''
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    data TEXT,
    timestamp TEXT,
    company TEXT,
    email TEXT
)
''')
conn.commit()

# ---------------- EMAIL OTP FUNCTION ----------------
def send_otp(email, otp):
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        sender_email = 'salesinsightsotp@gmail.com'
        sender_password = 'lgyehrzaxsllbdjt'  # Gmail App password
        server.login(sender_email, sender_password)
        message = f"Subject: OTP Verification\n\nYour OTP is: {otp}"
        server.sendmail(sender_email, email, message)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error sending email: {e}")
        return False

# ---------------- SESSION STATE ----------------
for key in ["logged_in", "role", "email", "company", "otp_sent", "otp_verified"]:
    if key not in st.session_state:
        st.session_state[key] = False

# ---------------- UTILITY FUNCTIONS ----------------
def add_sale(product, revenue, quantity):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO sales (company, product, revenue, quantity, timestamp) VALUES (?, ?, ?, ?, ?)",
              (st.session_state.company, product, revenue, quantity, timestamp))
    conn.commit()
    # Save to history
    c.execute("INSERT INTO history (action, data, timestamp, company, email) VALUES (?, ?, ?, ?, ?)",
              ("add", f"{product}|{revenue}|{quantity}", timestamp, st.session_state.company, st.session_state.email))
    conn.commit()

def delete_sale(sale_id):
    c.execute("SELECT product, revenue, quantity FROM sales WHERE id=? AND company=?",
              (sale_id, st.session_state.company))
    data = c.fetchone()
    if data:
        product, revenue, quantity = data
        c.execute("DELETE FROM sales WHERE id=? AND company=?", (sale_id, st.session_state.company))
        conn.commit()
        # Save to history
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO history (action, data, timestamp, company, email) VALUES (?, ?, ?, ?, ?)",
                  ("delete", f"{product}|{revenue}|{quantity}", timestamp, st.session_state.company, st.session_state.email))
        conn.commit()

def undo_last():
    c.execute("SELECT * FROM history WHERE email=? AND company=? ORDER BY id DESC LIMIT 1",
              (st.session_state.email, st.session_state.company))
    last = c.fetchone()
    if last:
        action, data = last[1], last[2]
        product, revenue, quantity = data.split("|")
        if action == "add":
            c.execute("DELETE FROM sales WHERE company=? AND product=? ORDER BY id DESC LIMIT 1",
                      (st.session_state.company, product))
        elif action == "delete":
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO sales (company, product, revenue, quantity, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (st.session_state.company, product, float(revenue), int(quantity), timestamp))
        conn.commit()
        c.execute("DELETE FROM history WHERE id=?", (last[0],))
        conn.commit()
        st.success("Last action undone!")
    else:
        st.info("No action to undo.")

def get_user_companies(email, role):
    c.execute("SELECT DISTINCT company FROM users WHERE email=? AND role=?", (email, role))
    return [row[0] for row in c.fetchall()]

# ---------------- SIDEBAR & LOGOUT ----------------
def render_sidebar():
    if st.session_state.logged_in:
        st.sidebar.subheader(f"{st.session_state.email} ({st.session_state.role})")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.role = None
            st.session_state.email = None
            st.session_state.company = None
            st.session_state.otp_sent = False
            st.session_state.otp_verified = False
            st.success("Logged out successfully! Please refresh the page to login again.")
        st.sidebar.markdown("---")

# ---------------- REGISTER PAGE ----------------
def register_page():
    st.subheader("Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["Admin", "Viewer"])
    company = st.text_input("Company Name")

    if st.button("Send OTP"):
        if role == "Admin":
            c.execute("SELECT * FROM users WHERE role='Admin' AND company=?", (company,))
            if c.fetchone():
                st.error(f"Admin already exists for {company}. Choose Viewer role instead.")
                return
        otp = str(random.randint(100000, 999999))
        if send_otp(email, otp):
            c.execute("INSERT OR REPLACE INTO users (email, password, role, company, otp) VALUES (?, ?, ?, ?, ?)",
                      (email, password, role, company, otp))
            conn.commit()
            st.success("OTP sent to your email.")
            st.session_state.otp_sent = True

    if st.session_state.otp_sent:
        otp_input = st.text_input("Enter OTP")
        if st.button("Verify OTP"):
            c.execute("SELECT otp FROM users WHERE email=?", (email,))
            real_otp = c.fetchone()[0]
            if otp_input == real_otp:
                c.execute("UPDATE users SET otp=NULL WHERE email=?", (email,))
                conn.commit()
                st.success("OTP verified! You can now login.")
                st.session_state.otp_verified = True

# ---------------- LOGIN PAGE ----------------
def login_page():
    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["Admin", "Viewer"])
    companies = get_user_companies(email, role)
    if companies:
        company = st.selectbox("Select Company", companies)
    else:
        st.warning("No companies found for this email and role.")
        return

    if st.button("Login"):
        c.execute("SELECT * FROM users WHERE email=? AND password=? AND role=? AND company=?",
                  (email, password, role, company))
        user = c.fetchone()
        if user:
            st.session_state.logged_in = True
            st.session_state.role = role
            st.session_state.email = email
            st.session_state.company = company
            st.success(f"Logged in as {role} for {company}")

# ---------------- RESET PASSWORD PAGE ----------------
def reset_password_page():
    st.subheader("Reset Password")
    email = st.text_input("Email")
    if st.button("Send OTP"):
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()
        if user:
            otp = str(random.randint(100000, 999999))
            if send_otp(email, otp):
                c.execute("UPDATE users SET otp=? WHERE email=?", (otp, email))
                conn.commit()
                st.success("OTP sent to your email. Enter below to reset password.")
                otp_input = st.text_input("Enter OTP")
                new_password = st.text_input("New Password", type="password")
                if st.button("Reset Password"):
                    c.execute("SELECT otp FROM users WHERE email=?", (email,))
                    real_otp = c.fetchone()[0]
                    if otp_input == real_otp:
                        c.execute("UPDATE users SET password=?, otp=NULL WHERE email=?", (new_password, email))
                        conn.commit()
                        st.success("Password reset successful! You can now login.")
                    else:
                        st.error("Incorrect OTP.")
        else:
            st.error("Email not registered.")

# ---------------- ADMIN DASHBOARD ----------------
def admin_dashboard():
    st.subheader(f"Admin Dashboard - {st.session_state.company}")
    st.write("Add new sales record:")
    product = st.text_input("Product")
    revenue = st.number_input("Revenue", min_value=0.0)
    quantity = st.number_input("Quantity", min_value=0)
    if st.button("Add Record"):
        if product and revenue and quantity:
            add_sale(product, revenue, quantity)
            st.success("Record added!")

    c.execute("SELECT * FROM sales WHERE company=?", (st.session_state.company,))
    data = c.fetchall()
    df = pd.DataFrame(data, columns=["ID", "Company", "Product", "Revenue", "Quantity", "Timestamp"])
    st.dataframe(df)

    sale_id = st.number_input("Enter Sale ID to delete", min_value=1)
    if st.button("Delete Record"):
        delete_sale(sale_id)
        st.success("Record deleted!")

    if st.button("Undo Last Action"):
        undo_last()

    if not df.empty:
        st.subheader("Analytics")
        st.bar_chart(df.groupby("Product")["Revenue"].sum())
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Export CSV", csv, "sales.csv", "text/csv")

# ---------------- VIEWER DASHBOARD ----------------
def viewer_dashboard():
    st.subheader(f"Viewer Dashboard - {st.session_state.company}")
    c.execute("SELECT * FROM sales WHERE company=?", (st.session_state.company,))
    data = c.fetchall()
    df = pd.DataFrame(data, columns=["ID", "Company", "Product", "Revenue", "Quantity", "Timestamp"])
    st.dataframe(df)

    if not df.empty:
        st.subheader("Analytics")
        st.bar_chart(df.groupby("Product")["Revenue"].sum())
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Export CSV", csv, "sales.csv", "text/csv")

# ---------------- LANDING PAGE ----------------
def landing_page():
    st.title("Sales Insights Dashboard")
    menu = ["Login", "Register", "Reset Password"]
    choice = st.sidebar.selectbox("Menu", menu)

    render_sidebar()  # show sidebar and logout if logged in

    if choice == "Register":
        register_page()
    elif choice == "Login":
        login_page()
    elif choice == "Reset Password":
        reset_password_page()

# ---------------- RUN APP ----------------
landing_page()

if st.session_state.logged_in:
    render_sidebar()
    if st.session_state.role == "Admin":
        admin_dashboard()
    else:
        viewer_dashboard()


