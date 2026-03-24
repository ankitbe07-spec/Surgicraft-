
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime
import calendar
import pandas as pd
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

st.set_page_config(page_title="Surgicraft Price List", layout="wide")

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
    "tc": "Surgicraft Internal Price List Record."
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return DEF_SETTINGS

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

settings = load_settings()

# --- SESSION STATE ---
if 'cart' not in st.session_state: st.session_state.cart = []
if 'q_no' not in st.session_state: st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_sheet():
    info = json.loads(st.secrets["google_key"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    client = gspread.authorize(creds)
    return client.open("Surgicraft_Database").sheet1

# Fetch data early for Auto-suggest Dropdowns
try:
    sheet = get_sheet()
    all_sheet_data = sheet.get_all_records()
    main_df = pd.DataFrame(all_sheet_data) if all_sheet_data else pd.DataFrame()
    
    unique_parties_list = sorted(main_df['Party'].astype(str).str.strip().str.title().unique().tolist()) if not main_df.empty else []
    unique_parts_list = sorted(main_df[main_df['Speed'] == 'Spare Part']['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    all_items_list = sorted(main_df['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
except Exception as e:
    st.error(f"Google Sheet Connection Error! Error: {e}")
    st.stop()

# --- HELPER FORMAT FUNCTION ---
def format_size(size_str):
    if "x" in size_str:
        parts = size_str.split('x')
        if len(parts) == 2:
            return f'{parts[0].strip()}" x {parts[1].strip()}"'
    return size_str

# --- HEADER WITH LOGO & GREEN TEXT ---
def display_header():
    col1, col2 = st.columns([1, 15])
    with col1:
        if os.path.exists("logo.png"):
            st.image("logo.png", width=60)
    with col2:
        st.markdown("<h1 style='margin-bottom: 0px; padding-bottom: 0px;'>Surgicraft Price List</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #00b300; font-weight: bold; margin-top: 0px;'>Created by Ankit Mistry</p>", unsafe_allow_html=True)
    st.write("---")

# --- PDF GENERATOR (History) ---
def create_history_pdf(party, records_df, period_str="Lifetime"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    c.setFont("Helvetica-Bold", 14); c.drawString(40, 800, f"Surgicraft Price List Record ({period_str})")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 775, f"Party Name: {party}")
    c.drawString(400, 775, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 740; c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Date"); c.drawString(110, y, "Description / Details"); c.drawString(460, y, "Amount (Rs)")
    c.line(40, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 11); grand_total = 0
    
    try:
        records_df['DateObj'] = pd.to_datetime(records_df['Date'], format="%d-%m-%Y", errors='coerce')
        records_df = records_df.sort_values('DateObj')
    except: pass

    for index, row in records_df.iterrows():
        date_str = str(row['Date'])
        size_str = format_size(str(row['Size']))
        speed_str = str(row['Speed'])
        total_price = int(row['Total_Price']) if pd.notna(row['Total_Price']) else 0
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, date_str)
        
        if speed_str == "Spare Part":
            c.drawString(110, y, f"Part: {size_str}")
            c.drawString(460, y, f"{total_price:,.2f}")
            grand_total += total_price; y -= 20
        else:
            base_price = int(settings['prices'].get(str(row['Size']), 0))
            c.drawString(110, y, f"Machine: {size_str}")
            if base_price > 0: c.drawString(460, y, f"{base_price:,.2f}")
            else: c.drawString(460, y, f"{total_price:,.2f}")
            y -= 16
            
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(120, y, f"• Speed: {speed_str}")
            y -= 16
            
            raw_addons = row.get('Options', '{}')
            addons_dict = {}
            if isinstance(raw_addons, str):
                try:
                    parsed = json.loads(raw_addons)
                    addons_dict = parsed if isinstance(parsed, dict) else {addon: 0 for addon in parsed}
                except: addons_dict = {raw_addons: 0}
            elif isinstance(raw_addons, list): addons_dict = {addon: 0 for addon in raw_addons}
            elif isinstance(raw_addons, dict): addons_dict = raw_addons

            for name, price in addons_dict.items():
                p_val = int(price) if price else 0
                c.drawString(120, y, f"• {name}")
                if p_val > 0: c.drawString(460, y, f"{p_val:,.2f}")
                y -= 16
                
            c.setFont("Helvetica-Bold", 10)
            c.drawString(120, y, "Total Price:")
            c.drawString(460, y, f"{total_price:,.2f}")
            grand_total += total_price; y -= 25
        
        if y < 80:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Date"); c.drawString(110, y, "Description / Details"); c.drawString(460, y, "Amount (Rs)")
            c.line(40, y-5, 550, y-5); y -= 25
        
    c.line(40, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y-25, f"{period_str.upper()} TOTAL VALUE: Rs. {grand_total:,.2f}/-")
    
    c.save(); buffer.seek(0)
    return buffer

# --- PDF GENERATOR (Search) ---
def create_part_search_pdf(party_name, part_name, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Surgicraft Item / Part Price Report")
    
    c.setFont("Helvetica", 11)
    c.drawString(40, 780, f"Party: {party_name if party_name and party_name != '-- All Parties --' else 'All Parties'}")
    c.drawString(40, 765, f"Item/Part: {part_name if part_name and part_name != '-- All Items --' else 'All Items'}")
    c.drawString(400, 780, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 730
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Date")
    c.drawString(120, y, "Party Name")
    c.drawString(280, y, "Item / Part Name")
    c.drawString(460, y, "Price (Rs)")
    c.line(40, y-5, 550, y-5)
    
    y -= 25
    c.setFont("Helvetica", 10)
    
    for index, row in df.iterrows():
        c.drawString(40, y, str(row['Date']))
        c.drawString(120, y, str(row['Party'])[:22])
        c.drawString(280, y, str(row['Size'])[:30])
        c.drawString(460, y, f"{int(row['Total_Price']):,.2f}")
        y -= 20
        
        if y < 80:
            c.showPage()
            y = 800
            c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Date")
            c.drawString(120, y, "Party Name")
            c.drawString(280, y, "Item / Part Name")
            c.drawString(460, y, "Price (Rs)")
            c.line(40, y-5, 550, y-5)
            y -= 25
            c.setFont("Helvetica", 10)
            
    c.save()
    buffer.seek(0)
    return buffer

# --- SIDEBAR MENU ---
st.sidebar.title("🏥 Surgicraft Menu")
menu = st.sidebar.radio("Go to:", ["➕ Add New Entry", "📜 Party History & Edit", "🔍 Part Price Finder", "⚙️ Master Settings"])

# ==========================================
# 1. ADD NEW ENTRY PAGE
# ==========================================
if menu == "➕ Add New Entry":
    display_header()
    
    party_sel = st.selectbox("Select Party (Type to search):", ["-- New Party --"] + unique_parties_list, index=0)
    if party_sel == "-- New Party --":
        party_name = st.text_input("Enter New Party Name:")
    else:
        party_name = party_sel
        
    st.write("---")
    
    entry_type = st.radio("What do you want to add?", ["Machine", "Spare Part / Custom Item"], horizontal=True)
    
    if entry_type == "Machine":
        col1, col2, col3 = st.columns(3)
        with col1:
            widths = sorted(list(set([k.split('x')[0] for k in settings['prices'].keys() if 'x' in k])))
            w_val = st.selectbox("Width", widths if widths else ["0"])
        with col2:
            lengths = sorted(list(set([k.split('x')[1] for k in settings['prices'].keys() if 'x' in k])))
            l_val = st.selectbox("Length", lengths if lengths else ["0"])
        with col3:
            speed = st.selectbox("Speed", ["Low", "High", "Low+High"])

        size = f"{w_val}x{l_val}"
        
        st.write("### Add-ons")
        cols = st.columns(3)
        selected_addons = []
        addons_prices_struct = {} 
        col_idx = 0
        
        if speed == "Low+High":
            lh_price = settings['addons'].get("LowHighExtra", 0)
            addons_prices_struct["Low+High Speed Extra"] = lh_price
            
        for addon_name in settings['addons']:
            if addon_name in ["LowHighExtra"]: continue
            if cols[col_idx % 3].checkbox(addon_name):
                selected_addons.append(addon_name)
                addons_prices_struct[addon_name] = settings['addons'].get(addon_name, 0)
            col_idx += 1

        base_machine_price = int(settings['prices'].get(size, 0))
        
        if base_machine_price == 0:
            st.error(f"Base price not found for size {size}. Please add it in Master Settings.")
        else:
            final_total_price = base_machine_price + sum(addons_prices_struct.values())
            st.success(f"**Final Machine Price: Rs. {final_total_price:,.2f}/-**")

            if st.button("➕ SAVE ENTRY TO SHEET", type="primary"):
                if not party_name: st.warning("Please enter/select Party Name first!")
                else:
                    dt = datetime.now().strftime("%d-%m-%Y")
                    sheet.append_row([st.session_state.q_no, party_name, dt, size, speed, json.dumps(addons_prices_struct), final_total_price])
                    st.toast(f"{size} Machine Saved for {party_name}! ✅")
                    st.cache_resource.clear()
                    st.rerun()

    else:
        st.write("### Add Spare Part Details")
        c1, c2 = st.columns(2)
        
        with c1:
            part_sel = st.selectbox("Select Part (Type to search):", ["-- New Part --"] + unique_parts_list, index=0)
            if part_sel == "-- New Part --":
                part_name = st.text_input("Enter New Part Name / Description:")
            else:
                part_name = part_sel
                
        with c2:
            part_price = st.number_input("Final Price (Rs)", min_value=0, step=100)
        
        if st.button("➕ SAVE PART TO SHEET", type="primary"):
            if not party_name: st.warning("Please enter Party Name first!")
            elif not part_name or part_price <= 0: st.warning("Please enter Part Name and Price!")
            else:
                dt = datetime.now().strftime("%d-%m-%Y")
                sheet.append_row([st.session_state.q_no, party_name, dt, part_name, "Spare Part", "{}", part_price])
                st.toast(f"{part_name} Saved for {party_name}! ✅")
                st.cache_resource.clear()
                st.rerun()

# ==========================================
# 2. PARTY HISTORY & EDIT PAGE 
# ==========================================
elif menu == "📜 Party History & Edit":
    display_header()
    
    if main_df.empty: st.info("No records found in Google Sheet.")
    else:
        df = main_df.copy()
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        
        tab1, tab2, tab3 = st.tabs(["📜 View/Download PDF", "✏️ Edit Record", "❌ Delete Record"])
        
        with tab1:
            st.write("### Party Wise Record")
            pdf_party = st.selectbox("Select Party (Type to search):", ["-- Select Party --"] + unique_parties_list, key="pdf_party")
            if pdf_party != "-- Select Party --":
                party_df = df[df['Clean_Party'] == pdf_party].copy()
                st.dataframe(party_df[['Date', 'Size', 'Speed', 'Total_Price']].rename(columns={'Size':'Item/Machine', 'Total_Price':'Price (Rs)'}), use_container_width=True)
                
                if st.button(f"📄 Download {pdf_party}'s Record PDF"):
                    hist_pdf = create_history_pdf(pdf_party, party_df, "Lifetime Record")
                    st.download_button("📥 Click to Save PDF", data=hist_pdf, file_name=f"{pdf_party}_Record.pdf", mime="application/pdf")

        with tab2:
            st.write("### Edit Existing Record (By Party)")
            edit_party = st.selectbox("1. Select Party:", ["-- Select Party --"] + unique_parties_list, key="edit_party")
            
            if edit_party != "-- Select Party --":
                party_items = df[df['Clean_Party'] == edit_party].copy()
                party_items['Display'] = party_items['Date'].astype(str) + " | " + party_items['Size'].astype(str) + " | Rs. " + party_items['Total_Price'].astype(str)
                item_options = party_items['Display'].tolist()
                
                selected_display = st.selectbox("2. Select Specific Item to Edit:", item_options)
                
                if selected_display:
                    row_data = party_items[party_items['Display'] == selected_display].iloc[0]
                    
                    st.write("---")
                    st.write("**Update Details:**")
                    new_item = st.text_input("Edit Item/Machine Name:", value=row_data['Size'])
                    new_price = st.number_input("Edit Total Price (Rs):", value=int(row_data['Total_Price']), step=100)
                    
                    if st.button("💾 Update Record in Sheet", type="primary"):
                        all_values = sheet.get_all_values()
                        row_index_to_update = -1
                        
                        for i, row_vals in enumerate(all_values):
                            if i == 0: continue
                            if (row_vals[1].strip().title() == edit_party and 
                                row_vals[2] == str(row_data['Date']) and 
                                row_vals[3] == str(row_data['Size']) and 
                                str(row_vals[6]) == str(row_data['Total_Price'])):
                                row_index_to_update = i + 1 
                                break
                                
                        if row_index_to_update != -1:
                            sheet.update_cell(row_index_to_update, 4, new_item)
                            sheet.update_cell(row_index_to_update, 7, new_price)
                            st.success("Record Updated Successfully!")
                            st.cache_resource.clear()
                            st.rerun()
                        else:
                            st.error("Row not found. Ensure no identical duplicates exist.")

        with tab3:
            st.write("### Delete Record (By Party)")
            del_party = st.selectbox("1. Select Party:", ["-- Select Party --"] + unique_parties_list, key="del_party")
            
            if del_party != "-- Select Party --":
                del_items = df[df['Clean_Party'] == del_party].copy()
                del_items['Display'] = del_items['Date'].astype(str) + " | " + del_items['Size'].astype(str) + " | Rs. " + del_items['Total_Price'].astype(str)
                
                selected_del = st.selectbox("2. Select Item to Delete:", del_items['Display'].tolist())
                
                if selected_del:
                    del_row_data = del_items[del_items['Display'] == selected_del].iloc[0]
                    
                    if st.button("❌ Delete Permanently", type="primary"):
                        all_values = sheet.get_all_values()
                        row_index_to_del = -1
                        
                        for i, row_vals in enumerate(all_values):
                            if i == 0: continue
                            if (row_vals[1].strip().title() == del_party and 
                                row_vals[2] == str(del_row_data['Date']) and 
                                row_vals[3] == str(del_row_data['Size']) and 
                                str(row_vals[6]) == str(del_row_data['Total_Price'])):
                                row_index_to_del = i + 1 
                                break
                                
                        if row_index_to_del != -1:
                            sheet.delete_rows(row_index_to_del)
                            st.success("Record Deleted Successfully!")
                            st.cache_resource.clear()
                            st.rerun()
                        else:
                            st.error("Row not found.")

# ==========================================
# 3. PART PRICE FINDER PAGE 
# ==========================================
elif menu == "🔍 Part Price Finder":
    display_header()
    st.write("Dabba par click karo ane upar search box ma sidhu Naam lakhi shako cho.")
    
    if main_df.empty:
        st.info("No records found in Google Sheet.")
    else:
        df = main_df.copy()
        
        c1, c2 = st.columns(2)
        search_party_name = c1.selectbox("1. Select Party (Type to search):", ["-- All Parties --"] + unique_parties_list, index=0)
        search_part_name = c2.selectbox("2. Select Part / Item (Type to search):", ["-- All Items --"] + all_items_list, index=0)
        
        filtered_df = df.copy()
        
        if search_party_name != "-- All Parties --":
            filtered_df = filtered_df[filtered_df['Party'].astype(str).str.strip().str.title() == search_party_name]
        if search_part_name != "-- All Items --":
            filtered_df = filtered_df[filtered_df['Size'].astype(str).str.strip() == search_part_name]
            
        st.write("### Search Results")
        
        if search_party_name == "-- All Parties --" and search_part_name == "-- All Items --":
            st.info("Please select a Party or Part Name above to see results.")
        elif filtered_df.empty:
            st.warning("Aa naam thi koi entry mali nathi.")
        else:
            display_df = filtered_df[['Date', 'Party', 'Size', 'Total_Price']].copy()
            display_df.rename(columns={'Size': 'Item / Part Name', 'Total_Price': 'Price (Rs)'}, inplace=True)
            st.dataframe(display_df, use_container_width=True)
            
            if st.button("📄 Download Search Result PDF"):
                pdf_buffer = create_part_search_pdf(search_party_name, search_part_name, filtered_df)
                file_name = f"PriceSearch_Result.pdf"
                st.download_button("📥 Click Here to Download PDF", data=pdf_buffer, file_name=file_name, mime="application/pdf")

# ==========================================
# 4. MASTER SETTINGS PAGE
# ==========================================
elif menu == "⚙️ Master Settings":
    display_header()
    st.title("Master Settings 🔒")
    pwd_input = st.text_input("Enter Master Password:", type="password")
    
    if pwd_input != settings.get('password', '1234'):
        if pwd_input: st.error("❌ Incorrect Password!")
        st.stop()
        
    st.success("Access Granted!")
    tab1, tab2 = st.tabs(["Machine Prices", "Add-ons"])
    
    with tab1:
        st.subheader("Edit/Remove Sizes")
        prices = settings['prices']
        for size, price in list(prices.items()):
            cA, cB, cC = st.columns([2, 2, 1])
            cA.write(f"**{format_size(size)}**")
            prices[size] = cB.number_input("Price", value=price, step=1000, key=f"p_{size}", label_visibility="collapsed")
            if cC.button("❌ Remove", key=f"d_{size}"):
                del prices[size]; save_settings(settings); st.rerun()
                    
        st.write("---")
        c1, c2, c3 = st.columns(3)
        n_w = c1.text_input("Width (e.g. 24)")
        n_l = c2.text_input("Length (e.g. 48)")
        n_p = c3.number_input("Base Price", value=0, step=1000)
        if st.button("➕ Add New Size"):
            if n_w and n_l and n_p > 0:
                settings['prices'][f"{n_w}x{n_l}"] = n_p
                save_settings(settings); st.rerun()

    with tab2:
        st.subheader("Edit/Remove Add-ons")
        addons = settings['addons']
        for name, price in list(addons.items()):
            if name in ["LowHighExtra"]:
                cA, cB = st.columns([2, 3])
                cA.write(f"**{name}**")
                addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
            else:
                cA, cB, cC = st.columns([2, 2, 1])
                cA.write(f"**{name}**")
                addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
                if cC.button("❌ Remove", key=f"da_{name}"):
                    del addons[name]; save_settings(settings); st.rerun()
                        
        if st.button("💾 Save Add-on Changes", type="primary"): save_settings(settings); st.success("Updated!")
        st.write("---")
        c1, c2 = st.columns(2)
        new_a = c1.text_input("New Add-on Name")
        new_p = c2.number_input("Add-on Price", value=0, step=500)
        if st.button("➕ Add New Option"):
            if new_a and new_p > 0:
                settings['addons'][new_a] = new_p
                save_settings(settings); st.rerun()
