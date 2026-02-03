import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
import locale

# --- ZKUSÍME NASTAVIT ČEŠTINU ---
try:
    locale.setlocale(locale.LC_ALL, "cs_CZ.UTF-8")
except:
    try:
        locale.setlocale(locale.LC_ALL, "Czech_Czech Republic.1250")
    except:
        pass

# --- 1. KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Sklad Hnojiv", page_icon="🌱", layout="centered")

# --- 2. VZHLED (CSS) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #E0E0E0; }
    h1, h2, h3, h4, h5 { color: #2ECC71 !important; font-family: sans-serif; }
    div.stButton > button {
        background-color: #1E2329; color: #2ECC71; 
        border: 1px solid #2ECC71; border-radius: 8px; font-weight: bold;
    }
    div.stButton > button:hover {
        background-color: #2ECC71; color: #0E1117; border: 1px solid #2ECC71;
    }
    div.stButton > button[kind="primary"] {
        background-color: #2ECC71; color: #0E1117; border: none;
    }
    .stTabs [data-baseweb="tab-list"] { background-color: #1E2329; padding: 10px; border-radius: 10px 10px 0 0; gap: 5px; }
    .stTabs [data-baseweb="tab"] { color: #888888; font-weight: bold; }
    .stTabs [aria-selected="true"] { color: #2ECC71 !important; border-bottom-color: #2ECC71 !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox div, .stDateInput input {
        background-color: #262730 !important; color: white !important; border-radius: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. PŘIPOJENÍ K DB ---
@st.cache_resource
def init_connection():
    return psycopg2.connect(**st.secrets["postgres"])

def execute_query(query, params=None, fetch=False):
    conn = init_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetch:
            res = cur.fetchall()
            conn.commit()
            return res
        conn.commit()
        cur.close()
        return None
    except Exception as e:
        conn.rollback()
        st.error(f"Chyba databáze: {e}")
        return None

# --- KONTROLA STRUKTURY DB (PRO ŘAZENÍ) ---
def check_db_structure():
    # Zajistíme, že existuje sloupec 'poradi' v tabulce hnojivo
    try:
        execute_query("ALTER TABLE hnojivo ADD COLUMN IF NOT EXISTS poradi INTEGER DEFAULT 0")
    except:
        pass

check_db_structure()

# --- POMOCNÁ FUNKCE PRO HEZKÁ ČÍSLA ---
def clean_number(val):
    if val is None: return ""
    try:
        formatted = f"{float(val):g}"
        return formatted.replace(".", ",")
    except:
        return str(val)

# --- 4. HLAVNÍ LOGIKA ---
st.title("🌱 Sklad Hnojiv (Mobil)")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# A) PŘIHLAŠOVACÍ OBRAZOVKA
if not st.session_state['logged_in']:
    st.markdown("### 🔐 Přihlášení")
    try:
        data = execute_query("SELECT id, nazev FROM stredisko ORDER BY nazev", fetch=True)
        strediska_dict = {row[1]: row[0] for row in data} if data else {}
    except:
        strediska_dict = {}
        st.error("Nelze se připojit k databázi.")

    if strediska_dict:
        selected_name = st.selectbox("Středisko", list(strediska_dict.keys()))
        selected_id = strediska_dict[selected_name]
        username = st.text_input("Jméno")
        password = st.text_input("Heslo", type="password")
        
        if st.button("Vstoupit", type="primary", use_container_width=True):
            user_data = execute_query(
                "SELECT id, role FROM users WHERE username=%s AND password=%s AND stredisko_id=%s",
                (username, password, selected_id), fetch=True
            )
            if user_data:
                st.session_state['logged_in'] = True
                st.session_state['user_id'] = user_data[0][0]
                st.session_state['role'] = user_data[0][1]
                st.session_state['stredisko_id'] = selected_id
                st.session_state['stredisko_name'] = selected_name
                st.rerun()
            else:
                st.error("Neplatné údaje!")

# B) APLIKACE PRO PŘIHLÁŠENÉ
else:
    c1, c2 = st.columns([3, 1])
    c1.info(f"📍 {st.session_state['stredisko_name']}")
    if c2.button("Odhlásit"):
        st.session_state['logged_in'] = False; st.rerun()

    tab1, tab2, tab3 = st.tabs(["💧 MÍCHÁNÍ", "📦 SKLAD", "🧪 RECEPTY"])

    # --- TAB 1: MÍCHÁNÍ ---
    with tab1:
        st.header("Zapsat míchání")
        recepty = execute_query("SELECT id, nazev FROM recept WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
        
        if recepty:
            r_dict = {r[1]: r[0] for r in recepty}
            sel_r = st.selectbox("Recept:", list(r_dict.keys()))
            voda = st.number_input("Voda (litry):", min_value=0, step=100, value=1000, format="%d")
            datum = st.date_input("Datum míchání:", value=date.today(), format="DD.MM.YYYY")
            
            if st.button("✅ Uložit míchání", type="primary", use_container_width=True):
                execute_query("INSERT INTO michani (recept_id, datum, objem_vody_l) VALUES (%s, %s, %s)", (r_dict[sel_r], datum, voda))
                st.toast("Uloženo!", icon="✅")
        else:
            st.warning("Žádné recepty.")

    # --- TAB 2: SKLAD (HROMADNÁ INVENTURA + PŘÍJEM + ŘAZENÍ) ---
    with tab2:
        typ_skladu = st.radio("Akce:", ["📋 Hromadná inventura", "🚛 Příjem zboží (Jednotlivě)"], horizontal=True, label_visibility="collapsed")

        # --- 1. HROMADNÁ INVENTURA ---
        if typ_skladu == "📋 Hromadná inventura":
            st.subheader("Hromadná inventura")
            
            # 1. Datum pro všechny
            inv_datum = st.date_input("Datum inventury:", value=date.today(), format="DD.MM.YYYY")
            
            st.info("Zadejte zjištěné stavy. Nevyplněná pole se neuloží.")
            
            # 2. Načtení hnojiv seřazených dle pořadí
            # COALESCE(poradi, 999) zajistí, že co nemá pořadí, bude na konci
            hnojiva_list = execute_query("""
                SELECT id, nazev, jednotka 
                FROM hnojivo 
                WHERE stredisko_id=%s 
                ORDER BY COALESCE(poradi, 999) ASC, nazev ASC
            """, (st.session_state['stredisko_id'],), fetch=True)

            if hnojiva_list:
                with st.form("bulk_inventura_form"):
                    input_values = {}
                    
                    # Procházíme hnojiva a děláme inputy
                    for h_id, h_nazev, h_jedn in hnojiva_list:
                        col_a, col_b = st.columns([3, 2])
                        with col_a:
                            st.write(f"**{h_nazev}**")
                        with col_b:
                            # Používáme text_input s konverzí, protože number_input má default 0.00
                            # Chceme rozeznat "nic" (None) od "0"
                            val = st.number_input(
                                f"Stav ({h_jedn})", 
                                key=f"inv_{h_id}", 
                                min_value=0.0, 
                                step=10.0, 
                                value=None,  # Defaultně prázdné
                                placeholder="Zadej..."
                            )
                            input_values[h_id] = val
                    
                    st.markdown("---")
                    submitted = st.form_submit_button("💾 ULOŽIT CELOU INVENTURU", type="primary", use_container_width=True)
                    
                    if submitted:
                        count = 0
                        for hid, mnozstvi in input_values.items():
                            if mnozstvi is not None: # Uložíme jen to, co uživatel vyplnil
                                execute_query(
                                    "INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) VALUES (%s, %s, %s, 'inventura')",
                                    (hid, inv_datum, mnozstvi)
                                )
                                count += 1
                        
                        if count > 0:
                            st.toast(f"Uloženo {count} položek!", icon="✅")
                            # st.rerun() by tady vymazalo formulář, což je asi dobře
                        else:
                            st.warning("Nevyplnili jste žádné množství.")

        # --- 2. PŘÍJEM ZBOŽÍ (JEDNOTLIVĚ) ---
        else:
            st.subheader("Příjem zboží")
            hnojiva = execute_query("SELECT id, nazev FROM hnojivo WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
            
            if hnojiva:
                h_dict = {h[1]: h[0] for h in hnojiva}
                sel_h = st.selectbox("Hnojivo:", list(h_dict.keys()))
                mn = st.number_input("Množství (kg/l):", min_value=0.0, step=10.0, format="%g")
                dt = st.date_input("Datum pohybu:", value=date.today(), format="DD.MM.YYYY")
                
                if st.button("📥 Uložit PŘÍJEM", type="primary", use_container_width=True):
                    execute_query("INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) VALUES (%s, %s, %s, 'dodavka')", (h_dict[sel_h], dt, mn))
                    st.toast("Příjem uložen!", icon="🚚")

        # --- 3. ADMIN: ŘAZENÍ HNOJIV ---
        if st.session_state.get('role') == 'admin':
            with st.expander("⚙️ Správa pořadí hnojiv (Admin)"):
                st.info("Změňte čísla v sloupci 'Pořadí' a klikněte na Uložit změny.")
                
                # Načteme data do DataFrame
                data_hnojiva = execute_query("""
                    SELECT id, nazev, COALESCE(poradi, 0) as poradi 
                    FROM hnojivo 
                    WHERE stredisko_id=%s 
                    ORDER BY poradi ASC, nazev ASC
                """, (st.session_state['stredisko_id'],), fetch=True)
                
                if data_hnojiva:
                    df_hnojiva = pd.DataFrame(data_hnojiva, columns=["ID", "Název", "Pořadí"])
                    
                    # Data editor umožňuje editovat tabulku přímo
                    edited_df = st.data_editor(
                        df_hnojiva, 
                        column_config={
                            "ID": st.column_config.NumberColumn(disabled=True),
                            "Název": st.column_config.TextColumn(disabled=True),
                            "Pořadí": st.column_config.NumberColumn(min_value=0, step=1, help="Menší číslo = výše v seznamu")
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    if st.button("💾 Uložit nové pořadí"):
                        # Projdeme upravený dataframe a uložíme změny
                        for index, row in edited_df.iterrows():
                            # Porovnáme s původním, abychom neukládali zbytečně, ale update všech je bezpečnější pro konzistenci
                            execute_query("UPDATE hnojivo SET poradi=%s WHERE id=%s", (row['Pořadí'], row['ID']))
                        
                        st.toast("Pořadí aktualizováno!", icon="✅")
                        st.rerun()

        # --- HISTORIE ---
        st.markdown("---")
        st.subheader("Poslední pohyby")
        hist = execute_query("""
            SELECT di.id, di.datum, h.nazev, di.mnozstvi_kg_l, di.typ 
            FROM dodavky_inventura di JOIN hnojivo h ON di.hnojivo_id=h.id 
            WHERE h.stredisko_id=%s ORDER BY di.id DESC LIMIT 10
        """, (st.session_state['stredisko_id'],), fetch=True)
        
        if hist:
            df = pd.DataFrame(hist, columns=["ID", "Datum", "Hnojivo", "Množství", "Typ"])
            df["Datum"] = pd.to_datetime(df["Datum"]).dt.strftime("%d.%m.%Y")
            df["Množství"] = df["Množství"].apply(clean_number)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            with st.expander("🗑️ Smazat záznam (při chybě)"):
                opts = {}
                for r in hist:
                    datum_str = r[1].strftime("%d.%m.%Y")
                    label = f"{datum_str} | {r[2]} ({clean_number(r[3])} kg) - {r[4]}"
                    opts[label] = r[0]
                del_sel = st.selectbox("Vyber záznam:", list(opts.keys()))
                if st.button(f"❌ Smazat záznam"):
                    execute_query("DELETE FROM dodavky_inventura WHERE id=%s", (opts[del_sel],))
                    st.warning("Smazáno."); st.rerun()

    # --- TAB 3: RECEPTY DETAIL ---
    with tab3:
        st.header("Složení receptů")
        recepty = execute_query("SELECT id, nazev FROM recept WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
        if recepty:
            r_dict = {r[1]: r[0] for r in recepty}
            sel_view = st.selectbox("Zobrazit:", list(r_dict.keys()), key="v_r")
            
            # Zde také použijeme řazení podle pořadí, pokud existuje v recept_polozka
            # Ale ve webové verzi stačí podle názvu nebo tanku
            items = execute_query("""
                SELECT rp.tank, h.nazev, rp.mnozstvi_na_1000l, h.jednotka 
                FROM recept_polozka rp JOIN hnojivo h ON rp.hnojivo_id=h.id 
                WHERE rp.recept_id=%s ORDER BY rp.tank, h.nazev
            """, (r_dict[sel_view],), fetch=True)
            
            if items:
                c_a, c_b = st.columns(2)
                def make_nice_table(data_items):
                    if not data_items: return None
                    df_temp = pd.DataFrame(data_items, columns=["T", "Hnojivo", "Množství", "J."])
                    df_temp["Množství"] = df_temp["Množství"].apply(clean_number)
                    return df_temp[["Hnojivo", "Množství", "J."]]

                with c_a:
                    st.markdown("### 🔵 TANK A")
                    ta = [i for i in items if i[0] == 'A']
                    df_a = make_nice_table(ta)
                    if df_a is not None: st.table(df_a)
                    else: st.info("Prázdný")

                with c_b:
                    st.markdown("### 🟢 TANK B")
                    tb = [i for i in items if i[0] == 'B']
                    df_b = make_nice_table(tb)
                    if df_b is not None: st.table(df_b)
                    else: st.info("Prázdný")