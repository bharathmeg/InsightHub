import streamlit as st
import sqlite3
import pandas as pd
import smtplib
import random
from datetime import datetime

# ---------------- DATABASE ----------------
conn = sqlite3.connect("sales_dashboard.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    password TEXT,
    role TEXT,
    company TEXT,
    otp TEXT,
    UNIQUE(email, role, company)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    product TEXT,
    revenue REAL,
    quantity INTEGER,
    timestamp TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT,
    data TEXT,
    timestamp TEXT,
    company TEXT,
    email TEXT
)
""")
conn.commit()

# ---------------- SESSION STATE ----------------
defaults = {
    "logged_in": False,
    "email": "",
    "role": "",
    "company": "",
    "otp_sent": False
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------- EMAIL OTP ----------------
def send_otp(email, otp):
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(
            st.secrets["EMAIL_ADDRESS"],
            st.secrets["EMAIL_PASSWORD"]
        )
        msg = f"Subject: OTP Verification\n\nYour OTP is: {otp}"
        server.sendmail(st.secrets["EMAIL_ADDRESS"], email, msg)
        server.quit()
        return True
    except:
        st.error("OTP sending failed. Check secrets.")
        return False

# ---------------- HELPERS ----------------
def add_sale(product, revenue, quantity):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO sales VALUES (NULL,?,?,?,?,?)",
              (st.session_state.company, product, revenue, quantity, ts))
    conn.commit()

    c.execute("INSERT INTO history VALUES (NULL,?,?,?,?,?)",
              ("add", f"{product}|{revenue}|{quantity}", ts,
               st.session_state.company, st.session_state.email))
    conn.commit()

def delete_sale(sale_id):
    c.execute(
        "SELECT product,revenue,quantity FROM sales WHERE id=? AND company=?",
        (sale_id, st.session_state.company)
    )
    row = c.fetchone()
    if row:
        product, revenue, quantity = row
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        conn.commit()

        c.execute("INSERT INTO history VALUES (NULL,?,?,?,?,?)",
                  ("delete", f"{product}|{revenue}|{quantity}", ts,
                   st.session_state.company, st.session_state.email))
        conn.commit()

def undo_last():
    c.execute("""
    SELECT id, action, data FROM history
    WHERE email=? AND company=?
    ORDER BY id DESC LIMIT 1
    """, (st.session_state.email, st.session_state.company))
    row = c.fetchone()

    if not row:
        st.info("Nothing to undo")
        return

    hid, action, data = row
    product, revenue, quantity = data.split("|")

    if action == "add":
        c.execute("""
        DELETE FROM sales WHERE id = (
            SELECT id FROM sales
            WHERE company=? AND product=?
            ORDER BY id DESC LIMIT 1
        )
        """, (st.session_state.company, product))
    else:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO sales VALUES (NULL,?,?,?,?,?)",
                  (st.session_state.company, product,
                   float(revenue), int(quantity), ts))

    conn.commit()
    c.execute("DELETE FROM history WHERE id=?", (hid,))
    conn.commit()

def get_companies(email, role):
    c.execute("SELECT company FROM users WHERE email=? AND role=?",
              (email, role))
    return [x[0] for x in c.fetchall()]

# ---------------- REGISTER ----------------
def register_page():
    st.subheader("Register")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["Admin", "Viewer"])
    company = st.text_input("Company")

    if st.button("Send OTP"):
        if role == "Admin":
            c.execute("SELECT * FROM users WHERE role='Admin' AND company=?",
                      (company,))
            if c.fetchone():
                st.error("Admin already exists for this company")
                return

        otp = str(random.randint(100000, 999999))
        if send_otp(email, otp):
            c.execute("""
            INSERT OR REPLACE INTO users
            (email,password,role,company,otp)
            VALUES (?,?,?,?,?)
            """, (email, password, role, company, otp))
            conn.commit()
            st.session_state.otp_sent = True
            st.success("OTP sent")
            st.rerun()

    if st.session_state.otp_sent:
        user_otp = st.text_input("Enter OTP")
        if st.button("Verify OTP"):
            c.execute("SELECT otp FROM users WHERE email=?", (email,))
            row = c.fetchone()
            if row and user_otp == row[0]:
                c.execute("UPDATE users SET otp=NULL WHERE email=?", (email,))
                conn.commit()
                st.session_state.otp_sent = False
                st.success("Registration successful")
                st.rerun()
            else:
                st.error("Invalid OTP")

# ---------------- LOGIN ----------------
def login_page():
    st.subheader("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Role", ["Admin", "Viewer"])

    companies = get_companies(email, role)
    if not companies:
        st.warning("No companies found")
        return

    company = st.selectbox("Company", companies)

    if st.button("Login"):
        c.execute("""
        SELECT * FROM users
        WHERE email=? AND password=? AND role=? AND company=?
        """, (email, password, role, company))
        if c.fetchone():
            st.session_state.logged_in = True
            st.session_state.email = email
            st.session_state.role = role
            st.session_state.company = company
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid credentials")

# ---------------- DASHBOARDS ----------------
def admin_dashboard():
    st.subheader(f"Admin Dashboard – {st.session_state.company}")

    product = st.text_input("Product")
    revenue = st.number_input("Revenue", min_value=0.0)
    quantity = st.number_input("Quantity", min_value=0)

    if st.button("Add Record"):
        if product:
            add_sale(product, revenue, quantity)
            st.rerun()

    df = pd.read_sql("SELECT * FROM sales WHERE company=?",
                     conn, params=(st.session_state.company,))
    st.dataframe(df)

    if not df.empty:
        sale_id = st.number_input("Sale ID to delete", min_value=1)
        if st.button("Delete"):
            delete_sale(sale_id)
            st.rerun()

        if st.button("Undo"):
            undo_last()
            st.rerun()

        st.subheader("Analytics")
        st.bar_chart(df.groupby("product")["revenue"].sum())

def viewer_dashboard():
    st.subheader(f"Viewer Dashboard – {st.session_state.company}")
    df = pd.read_sql("SELECT * FROM sales WHERE company=?",
                     conn, params=(st.session_state.company,))
    st.dataframe(df)
    if not df.empty:
        st.bar_chart(df.groupby("product")["revenue"].sum())

# ---------------- MAIN ----------------
st.title("InsightHub – Sales Insights Dashboard")

menu = ["Login", "Register"]
choice = st.sidebar.selectbox("Menu", menu)

if not st.session_state.logged_in:
    if choice == "Register":
        register_page()
    else:
        login_page()
else:
    st.sidebar.success(f"{st.session_state.email} ({st.session_state.role})")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    if st.session_state.role == "Admin":
        admin_dashboard()
    else:
        viewer_dashboard()
