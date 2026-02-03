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
    /* Vylepšení tabulky pro lepší čitelnost */
    [data-testid="stDataEditor"] {
        border: 1px solid #333;
        border-radius: 5px;
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

def check_db_structure():
    try: execute_query("ALTER TABLE hnojivo ADD COLUMN IF NOT EXISTS poradi INTEGER DEFAULT 0")
    except: pass

check_db_structure()

def clean_number(val):
    if val is None: return ""
    try: return f"{float(val):g}".replace(".", ",")
    except: return str(val)

# --- 4. HLAVNÍ LOGIKA ---
st.title("🌱 Sklad Hnojiv (Mobil)")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# A) LOGIN
if not st.session_state['logged_in']:
    st.markdown("### 🔐 Přihlášení")
    try:
        data = execute_query("SELECT id, nazev FROM stredisko ORDER BY nazev", fetch=True)
        strediska_dict = {row[1]: row[0] for row in data} if data else {}
    except: strediska_dict = {}; st.error("Chyba DB")

    if strediska_dict:
        selected_name = st.selectbox("Středisko", list(strediska_dict.keys()))
        selected_id = strediska_dict[selected_name]
        u = st.text_input("Jméno"); p = st.text_input("Heslo", type="password")
        if st.button("Vstoupit", type="primary", use_container_width=True):
            ud = execute_query("SELECT id, role FROM users WHERE username=%s AND password=%s AND stredisko_id=%s", (u, p, selected_id), fetch=True)
            if ud:
                st.session_state['logged_in'] = True; st.session_state['role'] = ud[0][1]
                st.session_state['stredisko_id'] = selected_id; st.session_state['stredisko_name'] = selected_name
                st.rerun()
            else: st.error("Neplatné údaje")

# B) APLIKACE
else:
    c1, c2 = st.columns([3, 1])
    c1.info(f"📍 {st.session_state['stredisko_name']}")
    if c2.button("Odhlásit"): st.session_state['logged_in'] = False; st.rerun()

    tab1, tab2, tab3 = st.tabs(["💧 MÍCHÁNÍ", "📦 SKLAD", "🧪 RECEPTY"])

    # --- TAB 1: MÍCHÁNÍ ---
    with tab1:
        st.header("Zapsat míchání")
        recepty = execute_query("SELECT id, nazev FROM recept WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
        if recepty:
            r_dict = {r[1]: r[0] for r in recepty}
            sel_r = st.selectbox("Recept:", list(r_dict.keys()))
            voda = st.number_input("Voda (l):", step=100, value=1000)
            datum = st.date_input("Datum:", value=date.today(), key="d_mix")
            if st.button("Uložit míchání", type="primary", use_container_width=True):
                execute_query("INSERT INTO michani (recept_id, datum, objem_vody_l) VALUES (%s, %s, %s)", (r_dict[sel_r], datum, voda))
                st.toast("Uloženo!", icon="✅")
        else: st.warning("Žádné recepty.")

    # --- TAB 2: SKLAD (TABULKA) ---
    with tab2:
        # PŘEJMENOVÁNO DLE POŽADAVKU
        mod = st.radio("Režim:", ["Inventura", "Příjem zboží"], horizontal=True, label_visibility="collapsed")

        # 1. INVENTURA JAKO TABULKA
        if mod == "Inventura":
            st.subheader("Hromadná inventura")
            inv_datum = st.date_input("Datum inventury:", value=date.today())
            st.info("Doplňte stavy do tabulky. Co necháte prázdné, to se neuloží.")

            # Načteme data seřazená podle pořadí
            hnojiva_data = execute_query("""
                SELECT id, nazev, jednotka 
                FROM hnojivo WHERE stredisko_id=%s 
                ORDER BY COALESCE(poradi, 999) ASC, nazev ASC
            """, (st.session_state['stredisko_id'],), fetch=True)

            if hnojiva_data:
                # Vytvoříme DataFrame pro editaci
                # Sloupec "Stav" necháme prázdný (None), aby uživatel viděl, co vyplnil
                df_source = pd.DataFrame(hnojiva_data, columns=["ID", "Hnojivo", "Jednotka"])
                df_source["Stav"] = None 

                # Zobrazíme editovatelnou tabulku
                edited_df = st.data_editor(
                    df_source,
                    column_config={
                        "ID": None, # Skryjeme ID
                        "Hnojivo": st.column_config.TextColumn(disabled=True), # Název nejde měnit
                        "Jednotka": st.column_config.TextColumn(disabled=True, width="small"),
                        "Stav": st.column_config.NumberColumn(
                            "Zjištěný stav", 
                            min_value=0, 
                            step=10, 
                            help="Zadejte množství",
                            required=False
                        )
                    },
                    hide_index=True,
                    use_container_width=True,
                    height=(len(hnojiva_data) * 35) + 38 # Dynamická výška
                )

                if st.button("💾 ULOŽIT INVENTURU", type="primary", use_container_width=True):
                    cnt = 0
                    for index, row in edited_df.iterrows():
                        # Uložíme jen řádky, kde uživatel něco vyplnil (není to NaN/None)
                        if pd.notna(row["Stav"]) and row["Stav"] != "":
                            execute_query(
                                "INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) VALUES (%s, %s, %s, 'inventura')",
                                (row["ID"], inv_datum, float(row["Stav"]))
                            )
                            cnt += 1
                    
                    if cnt > 0:
                        st.toast(f"Uloženo {cnt} položek!", icon="✅")
                        st.rerun() # Obnoví stránku a vymaže tabulku
                    else:
                        st.warning("Tabulka je prázdná.")

        # 2. PŘÍJEM ZBOŽÍ (JEDNOTLIVĚ)
        else:
            st.subheader("Příjem zboží")
            hd = execute_query("SELECT id, nazev FROM hnojivo WHERE stredisko_id=%s ORDER BY nazev", (st.session_state['stredisko_id'],), fetch=True)
            if hd:
                h_dict = {h[1]: h[0] for h in hd}
                sh = st.selectbox("Hnojivo:", list(h_dict.keys()))
                mn = st.number_input("Množství (+):", min_value=0.0, step=50.0)
                dt = st.date_input("Datum:", value=date.today())
                if st.button("Uložit PŘÍJEM", type="primary", use_container_width=True):
                    execute_query("INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) VALUES (%s, %s, %s, 'dodavka')", (h_dict[sh], dt, mn))
                    st.toast("Příjem uložen!", icon="🚚")

        # 3. ADMIN: ŘAZENÍ (TABULKA)
        if st.session_state.get('role') == 'admin':
            with st.expander("⚙️ Upravit pořadí hnojiv (Admin)"):
                st.caption("Přepište čísla v sloupci 'Pořadí' (1 = nahoře). Poté klikněte na Uložit.")
                
                # Načteme data pro admina
                dh = execute_query("SELECT id, nazev, COALESCE(poradi, 0) as poradi FROM hnojivo WHERE stredisko_id=%s ORDER BY poradi ASC, nazev ASC", (st.session_state['stredisko_id'],), fetch=True)
                
                if dh:
                    df_sort = pd.DataFrame(dh, columns=["ID", "Hnojivo", "Pořadí"])
                    
                    # Tabulka pro přepisování čísel (Drag&Drop nativně Streamlit neumí, toto je nejlepší alternativa)
                    edited_sort = st.data_editor(
                        df_sort,
                        column_config={
                            "ID": None,
                            "Hnojivo": st.column_config.TextColumn(disabled=True),
                            "Pořadí": st.column_config.NumberColumn(min_value=0, step=1, width="small")
                        },
                        hide_index=True,
                        use_container_width=True
                    )
                    
                    if st.button("✅ Uložit nové pořadí"):
                        for i, r in edited_sort.iterrows():
                            execute_query("UPDATE hnojivo SET poradi=%s WHERE id=%s", (r["Pořadí"], r["ID"]))
                        st.toast("Pořadí uloženo!", icon="🔄")
                        st.rerun()

        # HISTORIE
        st.markdown("---")
        hist = execute_query("SELECT di.id, di.datum, h.nazev, di.mnozstvi_kg_l, di.typ FROM dodavky_inventura di JOIN hnojivo h ON di.hnojivo_id=h.id WHERE h.stredisko_id=%s ORDER BY di.id DESC LIMIT 5", (st.session_state['stredisko_id'],), fetch=True)
        if hist:
            st.caption("Poslední pohyby:")
            for r in hist:
                icon = "📝" if r[4] == 'inventura' else "🚚"
                st.text(f"{icon} {r[1].strftime('%d.%m')} | {r[2]}: {clean_number(r[3])}")

    # --- TAB 3: RECEPTY ---
    with tab3:
        st.header("Složení receptů")
        if recepty:
            rv = st.selectbox("Recept:", list(r_dict.keys()), key="v_r")
            its = execute_query("SELECT rp.tank, h.nazev, rp.mnozstvi_na_1000l, h.jednotka FROM recept_polozka rp JOIN hnojivo h ON rp.hnojivo_id=h.id WHERE rp.recept_id=%s ORDER BY rp.tank, h.nazev", (r_dict[rv],), fetch=True)
            if its:
                ca, cb = st.columns(2)
                with ca:
                    st.info("🔵 TANK A")
                    st.table(pd.DataFrame([i for i in its if i[0]=='A'], columns=["T","Hnojivo","Množství","J."])[["Hnojivo","Množství","J."]])
                with cb:
                    st.info("🟢 TANK B")
                    st.table(pd.DataFrame([i for i in its if i[0]=='B'], columns=["T","Hnojivo","Množství","J."])[["Hnojivo","Množství","J."]])