import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
import locale

try:
    locale.setlocale(locale.LC_ALL, "cs_CZ.UTF-8")
except:
    try:
        locale.setlocale(locale.LC_ALL, "Czech_Czech Republic.1250") # Pro Windows
    except:
        pass # Pokud to nejde, zůstane angličtina

# --- 1. KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Sklad Hnojiv", page_icon="🌱", layout="centered")

# --- 2. VZHLED (CSS) ---
st.markdown("""
<style>
    /* Hlavní pozadí a text */
    .stApp { background-color: #0E1117; color: #E0E0E0; }

    /* Nadpisy */
    h1, h2, h3, h4, h5 { color: #2ECC71 !important; font-family: sans-serif; }

    /* Tlačítka */
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

    /* Záložky */
    .stTabs [data-baseweb="tab-list"] { background-color: #1E2329; padding: 10px; border-radius: 10px 10px 0 0; gap: 5px; }
    .stTabs [data-baseweb="tab"] { color: #888888; font-weight: bold; }
    .stTabs [aria-selected="true"] { color: #2ECC71 !important; border-bottom-color: #2ECC71 !important; }

    /* Inputy */
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
            voda = st.number_input("Voda (litry):", min_value=0, step=100, value=1000)
            
            # ZMĚNA: Formát data na DD.MM.YYYY
            datum = st.date_input("Datum míchání:", value=date.today(), format="DD.MM.YYYY")
            
            if st.button("✅ Uložit míchání", type="primary", use_container_width=True):
                execute_query("INSERT INTO michani (recept_id, datum, objem_vody_l) VALUES (%s, %s, %s)", (r_dict[sel_r], datum, voda))
                st.toast("Uloženo!", icon="✅")
        else:
            st.warning("Žádné recepty.")

    # --- TAB 2: SKLAD + HISTORIE ---
    with tab2:
        st.header("Pohyby hnojiv")
        akce = st.radio("Typ:", ["🚛 Příjem zboží (+)", "📝 Inventura (=)"], horizontal=True)
        hnojiva = execute_query("SELECT id, nazev FROM hnojivo WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
        
        if hnojiva:
            h_dict = {h[1]: h[0] for h in hnojiva}
            sel_h = st.selectbox("Hnojivo:", list(h_dict.keys()))
            mn = st.number_input("Množství (kg/l):", min_value=0.0, step=10.0)
            
            # ZMĚNA: Formát data na DD.MM.YYYY
            dt = st.date_input("Datum pohybu:", value=date.today(), format="DD.MM.YYYY")
            
            typ_sql = 'inventura' if "Inventura" in akce else 'dodavka'
            btn_lbl = "💾 Uložit INVENTURU" if "Inventura" in akce else "📥 Uložit PŘÍJEM"
            
            if st.button(btn_lbl, type="primary", use_container_width=True):
                execute_query("INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) VALUES (%s, %s, %s, %s)", (h_dict[sel_h], dt, mn, typ_sql))
                st.toast("Záznam uložen!", icon="💾"); st.rerun()

        st.markdown("---")
        st.subheader("Poslední pohyby")
        hist = execute_query("""
            SELECT di.id, di.datum, h.nazev, di.mnozstvi_kg_l, di.typ 
            FROM dodavky_inventura di JOIN hnojivo h ON di.hnojivo_id=h.id 
            WHERE h.stredisko_id=%s ORDER BY di.id DESC LIMIT 10
        """, (st.session_state['stredisko_id'],), fetch=True)
        
        if hist:
            df = pd.DataFrame(hist, columns=["ID", "Datum", "Hnojivo", "Množství", "Typ"])
            
            # ZMĚNA: Převedení data v tabulce na český formát (string)
            df["Datum"] = pd.to_datetime(df["Datum"]).dt.strftime("%d.%m.%Y")
            
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            with st.expander("🗑️ Smazat záznam (při chybě)"):
                # Do výběru pro mazání dáme také hezké datum
                opts = {}
                for r in hist:
                    # r[1] je datum objekt, převedeme ho na string
                    datum_str = r[1].strftime("%d.%m.%Y")
                    label = f"{datum_str} | {r[2]} ({r[3]} kg)"
                    opts[label] = r[0]
                    
                del_sel = st.selectbox("Vyber záznam:", list(opts.keys()))
                if st.button(f"❌ Smazat záznam"):
                    execute_query("DELETE FROM dodavky_inventura WHERE id=%s", (opts[del_sel],))
                    st.warning("Smazáno."); st.rerun()

    # --- TAB 3: RECEPTY DETAIL ---
    with tab3:
        st.header("Složení receptů")
        if recepty:
            sel_view = st.selectbox("Zobrazit:", list(r_dict.keys()), key="v_r")
            items = execute_query("""
                SELECT rp.tank, h.nazev, rp.mnozstvi_na_1000l, h.jednotka 
                FROM recept_polozka rp JOIN hnojivo h ON rp.hnojivo_id=h.id 
                WHERE rp.recept_id=%s ORDER BY rp.tank, h.nazev
            """, (r_dict[sel_view],), fetch=True)
            
            if items:
                c_a, c_b = st.columns(2)
                with c_a:
                    st.markdown("### 🔵 TANK A")
                    ta = [i for i in items if i[0] == 'A']
                    if ta: st.table(pd.DataFrame(ta, columns=["T", "Hnojivo", "Množství", "J."])[["Hnojivo","Množství","J."]])
                with c_b:
                    st.markdown("### 🟢 TANK B")
                    tb = [i for i in items if i[0] == 'B']
                    if tb: st.table(pd.DataFrame(tb, columns=["T", "Hnojivo", "Množství", "J."])[["Hnojivo","Množství","J."]])

