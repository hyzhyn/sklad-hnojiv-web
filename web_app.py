import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
import locale

# --- NASTAVENÍ ČEŠTINY ---
try: locale.setlocale(locale.LC_ALL, "cs_CZ.UTF-8")
except:
    try: locale.setlocale(locale.LC_ALL, "Czech_Czech Republic.1250")
    except: pass

# --- 1. KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Sklad Hnojiv", page_icon="🌱", layout="centered")

# --- 2. CSS STYLOVÁNÍ (Vylepšený vzhled) ---
st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #E0E0E0; }
    h1, h2, h3, h4, h5 { color: #2ECC71 !important; font-family: sans-serif; }
    
    /* Vylepšení tlačítek */
    div.stButton > button {
        background-color: #1E2329; color: #2ECC71; 
        border: 1px solid #2ECC71; border-radius: 8px; font-weight: bold;
        padding: 0.5rem 1rem;
    }
    div.stButton > button:hover {
        background-color: #2ECC71; color: #0E1117; border: 1px solid #2ECC71;
    }
    div.stButton > button[kind="primary"] {
        background-color: #2ECC71; color: #0E1117; border: none;
    }

    /* Inputy - modernější vzhled */
    .stNumberInput input, .stTextInput input, .stSelectbox div {
        background-color: #262730 !important;
        color: white !important;
        border-radius: 8px;
        border: 1px solid #444;
    }
    
    /* Oddělovače */
    hr { margin-top: 0.5rem; margin-bottom: 0.5rem; border-color: #333; }
    
    /* Zarovnání textu v řádcích formuláře */
    .row-label {
        font-size: 1.1rem;
        font-weight: 600;
        padding-top: 10px;
        color: #fff;
    }
    .unit-label { color: #888; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# --- 3. DB PŘIPOJENÍ ---
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
        st.error(f"Chyba DB: {e}")
        return None

def check_db_structure():
    # Původní kontrola
    try: execute_query("ALTER TABLE hnojivo ADD COLUMN IF NOT EXISTS poradi INTEGER DEFAULT 0")
    except: pass
    
    # NOVÉ: Kontrola sloupce user_id pro míchání
    try: execute_query("ALTER TABLE michani ADD COLUMN IF NOT EXISTS user_id INTEGER")
    except: pass

check_db_structure()

def clean_number(val):
    if val is None: return ""
    try: return f"{float(val):g}".replace(".", ",")
    except: return str(val)

# --- 4. APLIKACE ---
st.title("🌱 Sklad Hnojiv (Mobil)")

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

# A) LOGIN
if not st.session_state['logged_in']:
    st.markdown("### 🔐 Přihlášení")
    try:
        d = execute_query("SELECT id, nazev FROM stredisko ORDER BY nazev", fetch=True)
        sd = {r[1]: r[0] for r in d} if d else {}
    except: sd = {}
    
    if sd:
        s_name = st.selectbox("Středisko", list(sd.keys()))
        u = st.text_input("Jméno")
        p = st.text_input("Heslo", type="password")
        if st.button("Vstoupit", type="primary", use_container_width=True):
            # Změna: Vybíráme ID i ROLE
            ud = execute_query("SELECT id, role FROM users WHERE username=%s AND password=%s AND stredisko_id=%s", (u, p, sd[s_name]), fetch=True)
            if ud:
                # Změna: Ukládáme user_id do session_state
                st.session_state.update({
                    'logged_in': True, 
                    'user_id': ud[0][0],   # Uložení ID uživatele
                    'role': ud[0][1], 
                    'stredisko_id': sd[s_name], 
                    'stredisko_name': s_name
                })
                st.rerun()
            else: st.error("Chyba")

# B) HLAVNÍ OBSAH
else:
    c1, c2 = st.columns([3, 1])
    c1.info(f"📍 {st.session_state['stredisko_name']}")
    if c2.button("Odhlásit"): st.session_state['logged_in'] = False; st.rerun()

    t1, t2, t3 = st.tabs(["💧 MÍCHÁNÍ", "📦 SKLAD", "🧪 RECEPTY"])

    # --- TAB 1: MÍCHÁNÍ ---
    with t1:
        st.header("Zapsat míchání")
        recs = execute_query("SELECT id, nazev FROM recept WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
        if recs:
            rd = {r[1]: r[0] for r in recs}
            sr = st.selectbox("Recept:", list(rd.keys()))
            vo = st.number_input("Voda (l):", step=100, value=1000)
            da = st.date_input("Datum:", value=date.today(), key="d_m")
            
            if st.button("Uložit míchání", type="primary", use_container_width=True):
                # Změna: Přidán user_id do INSERTu
                uid = st.session_state.get('user_id')
                execute_query(
                    "INSERT INTO michani (recept_id, datum, objem_vody_l, user_id) VALUES (%s, %s, %s, %s)", 
                    (rd[sr], da, vo, uid)
                )
                st.toast("Uloženo!", icon="✅")
        else: st.warning("Žádné recepty")

    # --- TAB 2: SKLAD (NOVÝ DESIGN) ---
    with t2:
        mod = st.radio("Režim:", ["Inventura", "Příjem zboží"], horizontal=True, label_visibility="collapsed")

        # 1. INVENTURA (FORMULÁŘOVÝ STYL)
        if mod == "Inventura":
            st.subheader("Hromadná inventura")
            idat = st.date_input("Datum inventury:", value=date.today())
            st.markdown("---")

            # Načtení dat
            hdata = execute_query("""
                SELECT id, nazev, jednotka 
                FROM hnojivo WHERE stredisko_id=%s 
                ORDER BY COALESCE(poradi, 999) ASC, nazev ASC
            """, (st.session_state['stredisko_id'],), fetch=True)

            if hdata:
                with st.form("inv_form"):
                    inputy = {}
                    for hid, hnaz, hjed in hdata:
                        # Vytvoříme dvousloupcový řádek
                        col_txt, col_inp = st.columns([2, 1])
                        
                        with col_txt:
                            # Název a jednotka hezky pod sebou nebo vedle sebe
                            st.markdown(f"<div class='row-label'>{hnaz}</div>", unsafe_allow_html=True)
                            st.markdown(f"<span class='unit-label'>{hjed}</span>", unsafe_allow_html=True)
                        
                        with col_inp:
                            # Input bez labelu (ten je vlevo), placeholder napoví
                            val = st.number_input(
                                "Množství", 
                                key=f"i_{hid}", 
                                min_value=0.0, 
                                step=10.0, 
                                value=None, 
                                label_visibility="collapsed",
                                placeholder="0"
                            )
                            inputy[hid] = val
                        
                        st.divider() # Tenká čára mezi položkami

                    if st.form_submit_button("💾 ULOŽIT INVENTURU", type="primary", use_container_width=True):
                        cnt = 0
                        for hid, val in inputy.items():
                            if val is not None: # Uložíme jen vyplněné
                                execute_query("INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) VALUES (%s, %s, %s, 'inventura')", (hid, idat, val))
                                cnt += 1
                        if cnt > 0: st.toast(f"Uloženo {cnt} položek!", icon="✅"); st.rerun()
                        else: st.warning("Nic nebylo vyplněno.")

        # 2. PŘÍJEM (JEDNOTLIVĚ)
        else:
            st.subheader("Příjem zboží")
            hd = execute_query("SELECT id, nazev FROM hnojivo WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
            if hd:
                hd_dict = {h[1]: h[0] for h in hd}
                sh = st.selectbox("Hnojivo:", list(hd_dict.keys()))
                mn = st.number_input("Množství (+):", min_value=0.0, step=50.0)
                dt = st.date_input("Datum:", value=date.today())
                if st.button("Uložit PŘÍJEM", type="primary", use_container_width=True):
                    execute_query("INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) VALUES (%s, %s, %s, 'dodavka')", (hd_dict[sh], dt, mn))
                    st.toast("Příjem uložen!", icon="🚚")

        # 3. ADMIN: ŘAZENÍ (SEZNAM INPUTŮ)
        if st.session_state.get('role') == 'admin':
            with st.expander("⚙️ Upravit pořadí hnojiv (Admin)"):
                st.caption("Změňte čísla pro seřazení (1 = první nahoře).")
                adh = execute_query("SELECT id, nazev, COALESCE(poradi, 0) FROM hnojivo WHERE stredisko_id=%s ORDER BY poradi ASC, nazev ASC", (st.session_state['stredisko_id'],), fetch=True)
                
                if adh:
                    with st.form("sort_form"):
                        sort_map = {}
                        for ahid, ahnaz, ahpor in adh:
                            ac1, ac2 = st.columns([3, 1])
                            ac1.write(f"**{ahnaz}**")
                            # Malé políčko pro číslo pořadí
                            new_p = ac2.number_input("Pořadí", value=ahpor, min_value=0, step=1, key=f"sort_{ahid}", label_visibility="collapsed")
                            sort_map[ahid] = new_p
                        
                        if st.form_submit_button("✅ Uložit pořadí"):
                            for shid, sval in sort_map.items():
                                execute_query("UPDATE hnojivo SET poradi=%s WHERE id=%s", (sval, shid))
                            st.toast("Pořadí aktualizováno!", icon="🔄")
                            st.rerun()

        # HISTORIE
        st.markdown("---")
        hist = execute_query("SELECT di.id, di.datum, h.nazev, di.mnozstvi_kg_l, di.typ FROM dodavky_inventura di JOIN hnojivo h ON di.hnojivo_id=h.id WHERE h.stredisko_id=%s ORDER BY di.id DESC LIMIT 5", (st.session_state['stredisko_id'],), fetch=True)
        if hist:
            for r in hist:
                icon = "📝" if r[4] == 'inventura' else "🚚"
                st.text(f"{icon} {r[1].strftime('%d.%m')} | {r[2]}: {clean_number(r[3])}")

    # --- TAB 3: RECEPTY ---
    with t3:
        st.header("Složení receptů")
        if recs:
            rv = st.selectbox("Recept:", list(rd.keys()), key="v_r")
            its = execute_query("SELECT rp.tank, h.nazev, rp.mnozstvi_na_1000l, h.jednotka FROM recept_polozka rp JOIN hnojivo h ON rp.hnojivo_id=h.id WHERE rp.recept_id=%s ORDER BY rp.tank, h.nazev", (rd[rv],), fetch=True)
            if its:
                ca, cb = st.columns(2)
                with ca:
                    st.info("🔵 TANK A")
                    st.table(pd.DataFrame([i for i in its if i[0]=='A'], columns=["T","Hnojivo","Množství","J."])[["Hnojivo","Množství","J."]])
                with cb:
                    st.info("🟢 TANK B")
                    st.table(pd.DataFrame([i for i in its if i[0]=='B'], columns=["T","Hnojivo","Množství","J."])[["Hnojivo","Množství","J."]])