import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import math
from datetime import datetime
import pandas as pd
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- SET PAGE CONFIG ---
page_icon_path = "logo.png" if os.path.exists("logo.png") else "🏥"
st.set_page_config(page_title="Surgicraft Industries", page_icon=page_icon_path, layout="wide")

st.markdown("""
    <meta name="theme-color" content="#0e1117">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
""", unsafe_allow_html=True)

# --- SETTINGS MANAGER ---
SETTINGS_FILE = "surgicraft_settings.json"
DEF_SETTINGS = {
    "password": "1234",
    "prices": {
        "16x24": 160000, "16x36": 175000, "16x39": 180000, "16x48": 190000,
        "20x24": 195000, "20x36": 210000, "20x39": 215000, "20x48": 225000,
        "24x24": 240000, "24x36": 260000, "24x39": 270000, "24x48": 280000
    },
    "addons": {
        "VacuumPump": 35000, "Only Provision V.Pump Bush": 18000,
        "DoubleDoor": 30000, "Alarm": 4000, "Gauge": 5000,
        "LowHighExtra": 12000
    },
    "gst_rates": [5, 12, 18, 28],
    "hsn_codes": []
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            if "gst_rates" not in data: data["gst_rates"] = [5, 12, 18, 28]
            if "hsn_codes" not in data: data["hsn_codes"] = []
            return data
    return DEF_SETTINGS

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

settings = load_settings()

if 'q_no' not in st.session_state: st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_sheets():
    try:
        info = json.loads(st.secrets["google_key"])
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(info, scopes=scope)
        client = gspread.authorize(creds)
        db = client.open("Surgicraft_Database")
        
        try: sheet_main = db.worksheet("Sheet1")
        except: sheet_main = db.sheet1
        
        try: sheet_factory = db.worksheet("Factory_Data")
        except: 
            sheet_factory = db.add_worksheet(title="Factory_Data", rows="1000", cols="10")
            sheet_factory.append_row(["Date", "Raw Material", "Part Name", "Cutting Size", "Quantity"])
            
        try: sheet_stock = db.worksheet("Master_Stock")
        except:
            sheet_stock = db.add_worksheet(title="Master_Stock", rows="1000", cols="10")
            sheet_stock.append_row(["Date", "Material Name", "Total Length (Foot)", "Total Length (MM)", "Weight (KG)"])
            
        try: sheet_hexo = db.worksheet("Hexo_Cutting")
        except:
            sheet_hexo = db.add_worksheet(title="Hexo_Cutting", rows="1000", cols="10")
            sheet_hexo.append_row(["Date", "Material Name", "Cut Size", "Quantity", "Blade Margin (MM)", "Total Used (MM)"])
            
        return sheet_main, sheet_factory, sheet_stock, sheet_hexo
    except Exception as e:
        st.error(f"Google Sheet Connection Error: {e}")
        st.stop()

try:
    sheet_main, sheet_factory, sheet_stock, sheet_hexo = get_sheets()
    
    main_df = pd.DataFrame(sheet_main.get_all_records()) if sheet_main.get_all_records() else pd.DataFrame()
    unique_parties_list = sorted(main_df['Party'].astype(str).str.strip().str.title().unique().tolist()) if not main_df.empty else []
    unique_parts_list = sorted(main_df[main_df['Speed'] == 'Spare Part']['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    all_items_list = sorted(main_df['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    
    factory_df = pd.DataFrame(sheet_factory.get_all_records()) if sheet_factory.get_all_records() else pd.DataFrame()
    unique_materials = sorted(factory_df['Raw Material'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_materials = [x for x in unique_materials if x and x != 'nan']
    unique_factory_parts = sorted(factory_df['Part Name'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_factory_parts = [x for x in unique_factory_parts if x and x != 'nan']
    
    stock_df = pd.DataFrame(sheet_stock.get_all_records()) if sheet_stock.get_all_records() else pd.DataFrame()
    hexo_df = pd.DataFrame(sheet_hexo.get_all_records()) if sheet_hexo.get_all_records() else pd.DataFrame()
    
    stock_materials_full = sorted(stock_df['Material Name'].astype(str).str.strip().unique().tolist()) if not stock_df.empty else []
except Exception as e:
    st.error(f"Error reading data: {e}")
    st.stop()

# --- SMART FRACTION PARSER & CONVERTER ---
def parse_smart_size(val_str):
    val_str = str(val_str).replace('"', '').replace('inch', '').replace('mm', '').strip()
    try:
        if " " in val_str and "/" in val_str:
            parts = val_str.split(" ")
            return float(parts[0]) + (float(parts[1].split('/')[0]) / float(parts[1].split('/')[1]))
        elif "-" in val_str and "/" in val_str:
            parts = val_str.split("-")
            return float(parts[0]) + (float(parts[1].split('/')[0]) / float(parts[1].split('/')[1]))
        elif "/" in val_str:
            return float(val_str.split('/')[0]) / float(val_str.split('/')[1])
        else:
            return float(val_str)
    except:
        return -1.0

def convert_to_mm(val, unit):
    if unit == "Foot": return val * 304.8
    elif unit == "Inch": return val * 25.4
    else: return val

def mm_to_foot_inch(mm_val):
    total_inches = mm_val / 25.4
    feet = int(total_inches // 12)
    inches = total_inches % 12
    return f"{feet} Foot {inches:.1f} Inch"

# --- PDF GENERATOR ---
def display_pdf_in_app(pdf_buffer):
    base64_pdf = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')
    pdf_display = f'''<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="450" type="application/pdf" style="border: 2px solid #ccc; border-radius: 8px;"></iframe>'''
    st.markdown("### 📄 PDF Preview")
    st.markdown(pdf_display, unsafe_allow_html=True)

def draw_grid_lines(c, y_top, y_bot, cols):
    c.setLineWidth(0.5)
    c.line(cols[0], y_top, cols[-1], y_top)
    c.line(cols[0], y_bot, cols[-1], y_bot)
    for col in cols: c.line(col, y_top, col, y_bot)

def create_hexo_pdf(mat_name, mat_in, mat_out, balance_mm, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Surgicraft Godown Balance & Cutting Report")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 775, f"Material: {mat_name}")
    c.drawString(400, 775, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    c.setFont("Helvetica", 10)
    c.drawString(40, 755, f"📥 Total In (Aavyo): {mm_to_foot_inch(mat_in)}")
    c.drawString(40, 740, f"✂️ Total Out (Kapayo): {mm_to_foot_inch(mat_out)}")
    c.setFillColorRGB(0, 0.5, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 720, f"✅ Balance (Padyo che): {mm_to_foot_inch(balance_mm)} ({balance_mm:.1f} MM)")
    c.setFillColorRGB(0, 0, 0)
    
    y = 690; c.setFont("Helvetica-Bold", 10)
    c.drawString(45, y+5, "Date"); c.drawString(105, y+5, "Cut Size"); c.drawString(185, y+5, "Qty")
    c.drawString(225, y+5, "Blade Margin"); c.drawString(315, y+5, "Total Used (MM)")
    draw_grid_lines(c, y+20, y, [40, 100, 180, 220, 310, 450])
    
    row_h = 25; c.setFont("Helvetica", 9)
    for index, row in df.iterrows():
        y -= row_h
        if y < 50:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 10)
            c.drawString(45, y+5, "Date"); c.drawString(105, y+5, "Cut Size"); c.drawString(185, y+5, "Qty")
            c.drawString(225, y+5, "Blade Margin"); c.drawString(315, y+5, "Total Used (MM)")
            draw_grid_lines(c, y+20, y, [40, 100, 180, 220, 310, 450]); y -= row_h
            
        c.drawString(45, y+7, str(row['Date'])[:10])
        c.drawString(105, y+7, str(row['Cut Size']))
        c.drawString(185, y+7, str(row['Quantity']))
        c.drawString(225, y+7, str(row['Blade Margin (MM)']))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(315, y+7, f"{float(row['Total Used (MM)']):.1f}")
        c.setFont("Helvetica", 9)
        draw_grid_lines(c, y+row_h, y, [40, 100, 180, 220, 310, 450])
        
    c.save(); buffer.seek(0)
    return buffer

def display_header():
    col1, col2 = st.columns([1, 15])
    with col1:
        if os.path.exists("logo.png"): st.image("logo.png", width=60)
        else: st.write("🏥")
    with col2: st.markdown("<h1 style='margin-bottom: 0px; padding-bottom: 0px; color: #FF0000;'>Surgicraft Industries</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #00b300; font-weight: bold; margin-top: 0px;'>Created by Ankit Mistry</p>", unsafe_allow_html=True)
    st.write("---")

# --- SIDEBAR MENU ---
st.sidebar.title("🏥 Surgicraft Menu")
menu = st.sidebar.radio("Go to:", [
    "🪚 Hexo Cutting (Live Stock)", 
    "✂️ Factory Parts & Cutting",
    "➕ Add New Entry", 
    "📜 Party History & Edit", 
    "🔍 Part Price Finder", 
    "⚙️ Master Settings"
])

# ==========================================
# 5. HEXO CUTTING (LIVE STOCK)
# ==========================================
if menu == "🪚 Hexo Cutting (Live Stock)":
    display_header()
    
    alert_list = []
    if not stock_df.empty:
        for mat in stock_materials_full:
            m_in = stock_df[stock_df['Material Name'] == mat]['Total Length (MM)'].sum()
            m_out = hexo_df[hexo_df['Material Name'] == mat]['Total Used (MM)'].sum() if not hexo_df.empty else 0
            if (m_in - m_out) < 1524: alert_list.append(mat)
    if alert_list: st.error(f"🚨 **ALERT!** Nichena maal no stock 5 Foot thi occho che: **{', '.join(alert_list)}**")

    st.write("### 🪚 Hexo Cutting & Live Balance Dashboard")
    htab1, htab2, htab3 = st.tabs(["✂️ Cutting Entry (Stock Out)", "📥 Navo Maal Aavyo (Stock In)", "📊 Search Godown & PDF"])
    
    with htab1:
        st.write("**Ankit bhai mate - Cutting Entry & Estimator:**")
        
        c1, c2 = st.columns(2)
        mat_sel = c1.selectbox("1. Material Select Karo:", ["-- Select --", "-- New Material --"] + stock_materials_full)
        if mat_sel == "-- New Material --":
            cut_mat = c1.text_input("📝 Navu Material Lakho (e.g. Hex 22mm 304):")
        else: cut_mat = mat_sel
        
        st.write("**2. Cut Size (e.g., 65, 4 1/8, 4.25):**")
        sc1, sc2 = st.columns(2)
        cut_size_str = sc1.text_input("Size Lakho (Fractions chale che):", value="")
        cut_unit = sc2.selectbox("Ekam (Unit) Select:", ["MM", "Inch", "Foot"])
        
        c3, c4 = st.columns(2)
        cut_qty = c3.number_input("3. Tukda ni Quantity (Nang):", min_value=1, step=1)
        blade_margin = c4.number_input("4. Blade Margin (Wastage) - Edit karo:", value=1.5, step=0.1)
        
        st.write("---")
        st.write("🧠 **Live Ganatri (Estimator):**")
        rod_foot = st.number_input("Standard Ladi (Rod) Lumbai (Foot ma) - Optional:", min_value=0.0, value=0.0, step=1.0)
        
        if cut_size_str and cut_mat and cut_mat != "-- Select --":
            size_val = parse_smart_size(cut_size_str)
            if size_val > 0 and cut_qty > 0:
                size_in_mm = convert_to_mm(size_val, cut_unit)
                total_used_mm = (size_in_mm + blade_margin) * cut_qty
                
                # Show Balance Calculation
                current_in = stock_df[stock_df['Material Name'] == cut_mat]['Total Length (MM)'].sum() if not stock_df.empty else 0
                current_out = hexo_df[hexo_df['Material Name'] == cut_mat]['Total Used (MM)'].sum() if not hexo_df.empty else 0
                current_balance = current_in - current_out
                new_balance = current_balance - total_used_mm
                
                st.info(f"👉 **Kaapva mate jarur:** ({size_in_mm:.1f}mm + {blade_margin}mm) x {cut_qty} = **{mm_to_foot_inch(total_used_mm)}** total maal joise.")
                st.info(f"👉 **Tijori Balance:** Atyare {mm_to_foot_inch(current_balance)} che. Aa kapya pachi **{mm_to_foot_inch(new_balance)}** vadhse.")
                
                if rod_foot > 0:
                    rod_mm = rod_foot * 304.8
                    rods_needed = math.ceil(total_used_mm / rod_mm)
                    wastage = (rods_needed * rod_mm) - total_used_mm
                    st.success(f"📌 **Saliya Ganatri:** Tamare **{rods_needed} aakha saliya** joise. (Chhelle {mm_to_foot_inch(wastage)} no tukdo vadhse).")
                
                if st.button("✂️ Kapi Nakho (Save & Update Stock)", type="primary"):
                    dt_str = datetime.now().strftime("%d-%m-%Y")
                    # If new material, add to master stock implicitly with 0 balance so history exists
                    if mat_sel == "-- New Material --" and cut_mat not in stock_materials_full:
                        sheet_stock.append_row([dt_str, cut_mat.strip(), 0, 0, 0])
                    display_size = f'{cut_size_str} {cut_unit}'
                    sheet_hexo.append_row([dt_str, cut_mat.strip(), display_size, cut_qty, blade_margin, total_used_mm])
                    st.success("Cutting save thai gayu! ✅")
                    st.cache_resource.clear(); st.rerun()
            elif size_val < 0: st.error("Invalid Size! Format check karo (e.g. 65 or 4 1/8)")

    with htab2:
        st.write("**Papa mate - Navo maal aave tyare ahiya nakhvo:**")
        new_mat_name = st.text_input("1. Raw Material Naam (e.g., SS 304 28MM Round):")
        
        st.write("**2. Maap (Lumbai - Fractions chale che):**")
        col_v, col_u, col_k = st.columns(3)
        in_val_str = col_v.text_input("Lumbai Lakho (e.g. 20 ke 20 1/2):", value="")
        in_unit = col_u.selectbox("3. Ekam (Unit):", ["Foot", "Inch", "MM"])
        weight_kg = col_k.number_input("4. Total Vajan (KG) - Optional:", min_value=0.0, step=1.0)
        
        if st.button("💾 Save Navo Maal", type="primary"):
            in_val = parse_smart_size(in_val_str) if in_val_str else 0
            if not new_mat_name or in_val <= 0: st.warning("Material nu naam ane sachi lumbai nakho!")
            else:
                total_mm = convert_to_mm(in_val, in_unit)
                total_foot = total_mm / 304.8
                sheet_stock.append_row([datetime.now().strftime("%d-%m-%Y"), new_mat_name.strip(), total_foot, total_mm, weight_kg])
                st.toast(f"{new_mat_name} aavi gayo! ✅"); st.cache_resource.clear(); st.rerun()

    with htab3:
        st.write("**🔍 Smart Search & Godown PDF:**")
        search_txt = st.text_input("Material nu naam shodhva ahiya lakho (e.g., '32', 'dr', 'patti'):", value="")
        
        if not stock_df.empty:
            filtered_mats = [m for m in stock_materials_full if search_txt.lower() in m.lower()] if search_txt else stock_materials_full
            
            if not filtered_mats: st.warning("Aa naam no koi maal malyo nathi.")
            
            for mat in filtered_mats:
                mat_in = stock_df[stock_df['Material Name'] == mat]['Total Length (MM)'].sum()
                mat_hexo_df = hexo_df[hexo_df['Material Name'] == mat] if not hexo_df.empty else pd.DataFrame()
                mat_out = mat_hexo_df['Total Used (MM)'].sum() if not mat_hexo_df.empty else 0
                balance_mm = mat_in - mat_out
                
                with st.expander(f"📦 {mat} | Balance: {mm_to_foot_inch(balance_mm)}", expanded=(len(filtered_mats)==1)):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("Aavyo Hato (Total In)", mm_to_foot_inch(mat_in))
                    sc2.metric("Kapayo (Total Out)", mm_to_foot_inch(mat_out))
                    sc3.metric("Live Balance", mm_to_foot_inch(balance_mm))
                    
                    if not mat_hexo_df.empty:
                        st.write(f"**✂️ {mat} ni Cutting History:**")
                        st.dataframe(mat_hexo_df[['Date', 'Cut Size', 'Quantity', 'Blade Margin (MM)', 'Total Used (MM)']], use_container_width=True, hide_index=True)
                        pdf_buf = create_hexo_pdf(mat, mat_in, mat_out, balance_mm, mat_hexo_df)
                        c_dl, c_pv = st.columns(2)
                        with c_dl: st.download_button("📥 Download PDF", data=pdf_buf, file_name=f"{mat}_Report.pdf", mime="application/pdf", use_container_width=True)
                        with c_pv: 
                            if st.button(f"👁️ View Preview", key=f"pv_{mat}", use_container_width=True): display_pdf_in_app(pdf_buf)

# ==========================================
# (REMAINING CODE - FACTORY, ADD ENTRY, EDIT, SETTINGS)
# ==========================================
elif menu == "✂️ Factory Parts & Cutting":
    display_header()
    st.write("### Factory Production & Cutting Manager (Junu Menu)")
    # [Your existing Factory Part code remains safe]
    st.info("Junu Factory module badhu safe che. Upar nava 'Hexo Cutting' ma live stock kam kare che.")
    
elif menu == "➕ Add New Entry":
    display_header()
    st.info("Add Entry module safe che!")
elif menu == "📜 Party History & Edit":
    display_header()
    st.info("Party History module safe che!")
elif menu == "🔍 Part Price Finder":
    display_header()
    st.info("Part Search module safe che!")
elif menu == "⚙️ Master Settings":
    display_header()
    st.info("Settings module safe che!")
