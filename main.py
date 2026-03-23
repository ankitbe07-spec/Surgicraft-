import streamlit as st
import sqlite3
import json
import os
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- PAGE CONFIG ---
st.set_page_config(page_title="Surgicraft Quotation", layout="wide")

DB_NAME = "surgicraft_web.db"

# --- DB INIT ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS quotations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 q_no TEXT, party TEXT, date TEXT, size TEXT, 
                 speed TEXT, options TEXT, total INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    def_prices = {
        "16x24": 160000, "16x36": 175000, "16x39": 180000, "16x48": 190000,
        "20x24": 195000, "20x36": 210000, "20x39": 215000, "20x48": 225000,
        "24x24": 240000, "24x36": 260000, "24x39": 270000, "24x48": 280000
    }
    def_addons = {
        "VacuumPump": 35000, "Only Provision V.Pump Bush": 18000,
        "DoubleDoor": 30000, "Alarm": 4000, "Gauge": 5000,
        "PressureSwitch": 6000, "LowHighExtra": 12000
    }
    
    c.execute("SELECT value FROM settings WHERE key='base_prices'")
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ('base_prices', json.dumps(def_prices)))
    
    defaults = {
        'addons': json.dumps(def_addons),
        'tc': "Terms: GST Extra, Transport Extra, Subject to Ahmedabad Jurisdiction.",
        'password': '1234'
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def get_setting(key, is_json=False):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone(); conn.close()
    if row: return json.loads(row[0]) if is_json else row[0]
    return {} if is_json else ""

def get_next_qno():
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT MAX(id) FROM quotations")
    max_id = c.fetchone()[0]; conn.close()
    next_id = 1 if max_id is None else max_id + 1
    return f"SUR/{datetime.now().year}/{next_id:03d}"

# --- PDF GEN ---
def create_multi_pdf(party, q_no, items, date_str):
    if not os.path.exists("quotations"): os.makedirs("quotations")
    path = f"quotations/{q_no.replace('/','_')}_{party}.pdf"
    
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 20); c.drawString(150, 790, "SURGICRAFT INDUSTRIES")
    c.setFont("Helvetica-Bold", 10); c.drawString(150, 775, "Manufacturers of Hospital Equipment | Since 1985")
    c.setFont("Helvetica", 9)
    c.drawString(150, 760, "Partners: Vijay Mistry, Ketan Mistry")
    c.drawString(150, 745, "Ram krishna compound, Opp. Muncipal labour quator, Behind Bharat petrol pump,")
    c.drawString(150, 730, "Near naroda fruit market, Naroda Road. Ahmedabad - 380025")
    c.setFont("Helvetica-Bold", 10); c.drawString(150, 715, "GSTIN: [Tamaro GST Number]")
    c.line(50, 700, 550, 700)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 670, f"Quotation No: {q_no}"); c.drawString(400, 670, f"Date: {date_str}"); c.drawString(50, 650, f"Party Name: {party}")
    
    y = 610; c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Sr."); c.drawString(80, y, "Machine Size")
    c.drawString(180, y, "Speed & Specifications"); c.drawString(450, y, "Net Price (Rs)")
    c.line(50, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 10); grand_total = 0
    for i, item in enumerate(items, 1):
        c.drawString(50, y, str(i)); c.drawString(80, y, item['size'])
        opts_str = f"Speed: {item['speed']} | " + ", ".join(item['options'])
        if len(opts_str) > 55: opts_str = opts_str[:52] + "..."
        c.drawString(180, y, opts_str); c.drawString(450, y, str(item['total']))
        grand_total += item['total']; y -= 20
        if y < 150: c.showPage(); y = 750
            
    c.line(50, y-5, 550, y-5); c.setFont("Helvetica-Bold", 12); c.drawString(50, y-25, f"GRAND TOTAL VALUE: Rs. {grand_total}/-")
    c.setFont("Helvetica-Oblique", 9); c.drawString(50, 50, get_setting('tc')); c.save()
    return path

# --- INITIALIZE ---
init_db()
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'qno' not in st.session_state:
    st.session_state.qno = get_next_qno()

# --- HEADER ---
st.markdown("<h1 style='text-align: center; color: #007AFF;'>SURGICRAFT INDUSTRIES</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray; font-style: italic;'>Created by . Ankit Mistry</p>", unsafe_allow_html=True)
st.divider()

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📝 Create Quotation", "🔍 Party History", "⚙️ Master Settings"])

# ==============================
# TAB 1: QUOTATION BUILDER
# ==============================
with tab1:
    party_name = st.text_input("Party Name:", placeholder="Enter party name here...")
    
    db_prices = get_setting('base_prices', True)
    w_list = sorted(list(set([k.split('x')[0] for k in db_prices.keys() if 'x' in k])), key=lambda x: int(x) if x.isdigit() else 0)
    l_list = sorted(list(set([k.split('x')[1] for k in db_prices.keys() if 'x' in k])), key=lambda x: int(x) if x.isdigit() else 0)
    
    st.markdown("### Machine Details")
    col1, col2, col3 = st.columns(3)
    with col1: w_val = st.selectbox("Width", w_list)
    with col2: l_val = st.selectbox("Length", l_list)
    with col3: sp_val = st.selectbox("Speed", ["Low", "High", "Low+High"])
    
    st.markdown("### Add-ons")
    a_data = get_setting('addons', True)
    selected_addons = []
    
    cols = st.columns(3)
    idx = 0
    for name in a_data:
        if name in ["LowHighExtra", "PressureSwitch"]: continue
        with cols[idx % 3]:
            if st.checkbox(name): selected_addons.append(name)
        idx += 1
        
    press_qty = st.selectbox("Pressure Switch Qty", [0, 1, 2])
    
    if st.button("➕ ADD TO PRICE LIST", type="primary", use_container_width=True):
        if not party_name:
            st.error("Party Name lakho!")
        else:
            size_str = f"{w_val}x{l_val}"
            total = db_prices.get(size_str, 0)
            if total == 0:
                st.error(f"{size_str} no bhav Master Settings ma nathi!")
            else:
                opts = list(selected_addons)
                if sp_val == "Low+High": total += a_data.get("LowHighExtra", 0)
                for a in selected_addons: total += a_data.get(a, 0)
                if press_qty > 0:
                    total += (press_qty * a_data.get("PressureSwitch", 0))
                    opts.append(f"{press_qty} Pressure Switch")
                
                # Save to DB
                dt = datetime.now().strftime("%d-%m-%Y")
                conn = sqlite3.connect(DB_NAME); c = conn.cursor()
                c.execute("INSERT INTO quotations (q_no, party, date, size, speed, options, total) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (st.session_state.qno, party_name, dt, size_str, sp_val, json.dumps(opts), total))
                conn.commit(); conn.close()
                
                # Add to session cart
                st.session_state.cart.append({"size": size_str, "speed": sp_val, "options": opts, "total": total})
                st.success("Item Added!")
                st.rerun()

    if st.session_state.cart:
        st.markdown("### Current Party Price List")
        for i, item in enumerate(st.session_state.cart, 1):
            st.info(f"{i}. **{item['size']}** | Speed: {item['speed']} | Rs. {item['total']}/-")
            
        dt = datetime.now().strftime("%d-%m-%Y")
        pdf_path = create_multi_pdf(party_name, st.session_state.qno, st.session_state.cart, dt)
        
        with open(pdf_path, "rb") as pdf_file:
            PDFbyte = pdf_file.read()
            
        if st.download_button(label="📥 GENERATE & DOWNLOAD PDF", data=PDFbyte, file_name=f"Quotation_{party_name}.pdf", mime='application/octet-stream', use_container_width=True):
            st.session_state.cart = []
            st.session_state.qno = get_next_qno()
            st.rerun()

# ==============================
# TAB 2: HISTORY
# ==============================
with tab2:
    st.markdown("### Search Party History")
    search_term = st.text_input("Enter Party Name to Search:")
    
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    if search_term:
        c.execute("SELECT id, date, q_no, party, size, total FROM quotations WHERE party LIKE ? ORDER BY id DESC", (f"%{search_term}%",))
    else:
        c.execute("SELECT id, date, q_no, party, size, total FROM quotations ORDER BY id DESC LIMIT 20")
    records = c.fetchall()
    conn.close()
    
    if records:
        for rec in records:
            st.write(f"**Date:** {rec[1]} | **Q.No:** {rec[2]} | **Party:** {rec[3]} | **Size:** {rec[4]} | **Price:** Rs.{rec[5]}")
            st.divider()
    else:
        st.write("Koi record nathi.")

# ==============================
# TAB 3: MASTER SETTINGS
# ==============================
with tab3:
    pwd = get_setting('password')
    entered_pwd = st.text_input("Enter Master Password:", type="password")
    
    if entered_pwd == pwd:
        st.success("Access Granted!")
        st.write("Navi Size ke Bhav badalva mate atyare PC/Mobile app no upyog karo. Database sync thase.")
        # Ahia advance settings aavi shake, pan mobile app (Pydroid) mathi manage karvu vadhu saral che.
    elif entered_pwd:
        st.error("Wrong Password!")

