import streamlit as st
import psycopg2
import pandas as pd
from datetime import date
import locale
import hashlib

# --- NASTAVENÍ ČEŠTINY ---
try: locale.setlocale(locale.LC_ALL, "cs_CZ.UTF-8")
except:
    try: locale.setlocale(locale.LC_ALL, "Czech_Czech Republic.1250")
    except: pass

# --- 1. KONFIGURACE STRÁNKY ---
st.set_page_config(
    page_title="Sklad Hnojiv",
    page_icon="🌱",
    layout="centered"
)

# --- 2. CSS STYLOVÁNÍ ---
st.markdown("""
<style>
    /* Pozadí a text */
    .stApp { background-color: #0f1117; color: #e2e8f0; }

    /* Nadpisy */
    h1, h2, h3, h4, h5 { color: #00c896 !important; font-family: 'Segoe UI', sans-serif; }

    /* Tlačítka */
    div.stButton > button {
        background-color: #1c2230;
        color: #e2e8f0;
        border: 1px solid #2d3748;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.45rem 1rem;
        transition: all 0.15s ease;
    }
    div.stButton > button:hover {
        background-color: #2d3748;
        border-color: #00c896;
        color: #00c896;
    }
    div.stButton > button[kind="primary"] {
        background-color: #00c896;
        color: #000;
        border: none;
        font-weight: 700;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #009e78;
    }

    /* Vstupní pole */
    .stNumberInput input, .stTextInput input {
        background-color: #1e2533 !important;
        color: #e2e8f0 !important;
        border-radius: 7px !important;
        border: 1px solid #2d3748 !important;
    }
    .stSelectbox > div > div {
        background-color: #1e2533 !important;
        color: #e2e8f0 !important;
        border: 1px solid #2d3748 !important;
        border-radius: 7px !important;
    }
    /* Datepicker */
    .stDateInput input {
        background-color: #1e2533 !important;
        color: #e2e8f0 !important;
        border: 1px solid #2d3748 !important;
    }

    /* Tabulky */
    .stDataFrame, .stTable { border-radius: 8px; overflow: hidden; }
    thead tr th { background-color: #0f1117 !important; color: #94a3b8 !important; font-size: 0.85rem !important; }
    tbody tr td { background-color: #161b22 !important; color: #e2e8f0 !important; }
    tbody tr:nth-child(odd) td { background-color: #1c2230 !important; }

    /* Oddělovač */
    hr { margin: 0.6rem 0; border-color: #2d3748; }

    /* Vlastní labely řádků hnojiv */
    .row-label { font-size: 1.05rem; font-weight: 600; padding-top: 8px; color: #e2e8f0; }
    .unit-label { color: #94a3b8; font-size: 0.88rem; }

    /* Info box */
    div[data-testid="stInfo"] {
        background-color: #1c2230;
        border-left: 3px solid #00c896;
        color: #e2e8f0;
    }

    /* Toast */
    div[data-testid="stToast"] {
        background-color: #1c2230;
        border: 1px solid #00c896;
        color: #e2e8f0;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { background-color: #0f1117; border-bottom: 1px solid #2d3748; }
    .stTabs [data-baseweb="tab"] { color: #94a3b8; font-weight: 600; }
    .stTabs [aria-selected="true"] { color: #00c896 !important; border-bottom: 2px solid #00c896 !important; }

    /* Radio */
    .stRadio > div { gap: 1rem; }

    /* Expander */
    details { border: 1px solid #2d3748 !important; border-radius: 8px !important; }
    summary { color: #94a3b8 !important; }
</style>
""", unsafe_allow_html=True)

# --- 3. HASHOVÁNÍ HESEL (stejný algoritmus jako desktop app) ---
def hash_password(password: str) -> str:
    """SHA-256 hash — stejná implementace jako v desktop aplikaci."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(plain: str, stored: str) -> bool:
    """
    Ověří heslo — podporuje jak hashovaná (nová) tak plain-text (stará) hesla.
    Pokud je heslo plain-text, automaticky ho upgraduje na hash.
    Vrací: (ok: bool, needs_upgrade: bool)
    """
    if hash_password(plain) == stored:
        return True, False   # Nový formát — OK
    if plain == stored:
        return True, True    # Starý plain-text — OK, ale upgradovat
    return False, False

# --- 4. DB PŘIPOJENÍ ---
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
            cur.close()
            return res
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        st.error(f"Chyba DB: {e}")
        return None

def check_db_structure():
    """Zajistí potřebné sloupce — bezpečně, jeden po druhém."""
    opravy = [
        "ALTER TABLE hnojivo ADD COLUMN IF NOT EXISTS poradi INTEGER DEFAULT 0",
        "ALTER TABLE michani ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cele_jmeno VARCHAR(150)",
        # VARCHAR(255) s USING — nerozhodí existující data
        "ALTER TABLE users ALTER COLUMN password TYPE VARCHAR(255) USING password::VARCHAR(255)",
        """CREATE TABLE IF NOT EXISTS sezona (
            id SERIAL PRIMARY KEY, nazev VARCHAR(50),
            datum_od DATE, datum_do DATE, stredisko_id INTEGER
        )""",
        "ALTER TABLE recept ADD COLUMN IF NOT EXISTS datum_vytvoreni DATE DEFAULT CURRENT_DATE",
    ]
    for sql in opravy:
        try:
            execute_query(sql)
        except:
            pass

check_db_structure()

# --- 5. POMOCNÉ FUNKCE ---
def format_num(val):
    if val is None: return ""
    try: return f"{float(val):g}".replace(".", ",")
    except: return str(val)

def format_date(d):
    if d is None: return ""
    try: return d.strftime("%d.%m.%Y")
    except: return str(d)

# --- 6. COOKIES (volitelné) ---
try:
    import extra_streamlit_components as stx
    cookie_manager = stx.CookieManager()
    saved_s = cookie_manager.get(cookie="rem_stredisko")
    saved_u = cookie_manager.get(cookie="rem_user")
    # BEZPEČNOST: heslo v cookies neukládáme — jen login
except ImportError:
    cookie_manager = None
    saved_s, saved_u = None, None

# --- 7. INICIALIZACE SESSION STATE ---
defaults = {
    'logged_in': False, 'user_id': None, 'role': None,
    'display_name': None, 'stredisko_id': None, 'stredisko_name': None,
    'mix_saved': False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════════════
# A) LOGIN
# ═══════════════════════════════════════════════════════════════
if not st.session_state['logged_in']:

    # Centrovaný login
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 🌱 Sklad Hnojiv")
        st.markdown("##### Přihlášení")
        st.markdown("---")

        strediska = execute_query("SELECT id, nazev FROM stredisko ORDER BY nazev", fetch=True)
        sd = {r[1]: r[0] for r in strediska} if strediska else {}

        if not sd:
            st.error("⚠ Nelze načíst střediska — zkontrolujte připojení k databázi.")
            st.stop()

        # Předvyplnění z cookies
        s_index = 0
        if saved_s and saved_s in sd:
            s_index = list(sd.keys()).index(saved_s)

        with st.form("login_form"):
            s_name = st.selectbox("Středisko", list(sd.keys()), index=s_index)
            u = st.text_input("Přihlašovací jméno", value=saved_u or "")
            p = st.text_input("Heslo", type="password")
            zapamatovat = st.checkbox(
                "Zapamatovat přihlašovací jméno",
                value=bool(saved_u),
                help="Heslo se z bezpečnostních důvodů neukládá"
            )
            submit = st.form_submit_button("Přihlásit se", type="primary", use_container_width=True)

            if submit:
                if not u or not p:
                    st.error("Zadejte jméno i heslo.")
                else:
                    # OPRAVA: Načteme heslo z DB a ověřujeme ho v Pythonu
                    # (NE přes SQL WHERE password=... — to nefunguje s hashi)
                    ud = execute_query(
                        "SELECT id, role, cele_jmeno, password FROM users "
                        "WHERE username=%s AND stredisko_id=%s",
                        (u, sd[s_name]), fetch=True
                    )
                    if ud:
                        uid, role, cele_jmeno, stored_pw = ud[0]
                        ok, needs_upgrade = verify_password(p, stored_pw)

                        if ok:
                            # Automatický upgrade plain-text hesla na hash
                            if needs_upgrade:
                                execute_query(
                                    "UPDATE users SET password=%s WHERE id=%s",
                                    (hash_password(p), uid)
                                )

                            display_name = cele_jmeno if cele_jmeno else u

                            st.session_state.update({
                                'logged_in': True,
                                'user_id': uid,
                                'role': role,
                                'display_name': display_name,
                                'stredisko_id': sd[s_name],
                                'stredisko_name': s_name,
                            })

                            # Cookies — ukládáme jen jméno střediska a login, NE heslo
                            if cookie_manager:
                                if zapamatovat:
                                    cookie_manager.set("rem_stredisko", s_name, max_age=31536000, key="set_s")
                                    cookie_manager.set("rem_user", u, max_age=31536000, key="set_u")
                                else:
                                    if saved_s: cookie_manager.delete("rem_stredisko", key="del_s")
                                    if saved_u: cookie_manager.delete("rem_user", key="del_u")

                            st.rerun()
                        else:
                            st.error("❌ Špatné heslo.")
                    else:
                        st.error("❌ Uživatel nenalezen nebo špatné středisko.")

# ═══════════════════════════════════════════════════════════════
# B) HLAVNÍ OBSAH
# ═══════════════════════════════════════════════════════════════
else:
    # Header — info lišta + odhlášení
    hcol1, hcol2 = st.columns([4, 1])
    hcol1.info(
        f"📍 **{st.session_state['stredisko_name']}**  ·  "
        f"👤 {st.session_state.get('display_name', '')}  ·  "
        f"🔑 {st.session_state.get('role', '')}"
    )
    if hcol2.button("🚪 Odhlásit"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.markdown("---")

    # Načtení receptů jednou pro celou session (sdílíme mezi taby)
    recs_raw = execute_query(
        "SELECT id, nazev FROM recept WHERE stredisko_id=%s ORDER BY nazev",
        (st.session_state['stredisko_id'],), fetch=True
    ) or []
    rd = {r[1]: r[0] for r in recs_raw}

    # ── Dialog potvrzení míchání ────────────────────────────────
    @st.dialog("⚠️ Potvrzení míchání")
    def ukaz_potvrzeni(recept_id, recept_nazev, datum, objem_vody, user_id):
        st.write(f"**Recept:** {recept_nazev}")
        st.write(f"**Voda:** {objem_vody:,} litrů")
        st.write(f"**Datum:** {format_date(datum)}")
        st.write("")
        c_ano, c_ne = st.columns(2)
        if c_ano.button("✅ Potvrdit", type="primary", use_container_width=True):
            res = execute_query(
                "INSERT INTO michani (recept_id, datum, objem_vody_l, user_id) VALUES (%s,%s,%s,%s)",
                (recept_id, datum, objem_vody, user_id)
            )
            if res:
                st.session_state['mix_saved'] = True
            st.rerun()
        if c_ne.button("❌ Storno", use_container_width=True):
            st.rerun()

    # ── Zobrazit toast po úspěšném míchání ─────────────────────
    if st.session_state.get('mix_saved'):
        st.toast("✅ Míchání bylo uloženo!", icon="💧")
        st.session_state['mix_saved'] = False

    # ── TABY ───────────────────────────────────────────────────
    t1, t2, t3, t4 = st.tabs(["💧 Míchání", "📦 Sklad", "🧪 Recepty", "📊 Bilance"])

    # ── TAB 1: MÍCHÁNÍ ─────────────────────────────────────────
    with t1:
        st.subheader("Zapsat míchání")

        uid = st.session_state.get('user_id')
        if uid is None:
            st.error("⛔ Systém ztratil ID uživatele — odhlaste se a přihlaste znovu.")
            st.stop()

        if not rd:
            st.warning("⚠ Žádné recepty pro toto středisko.")
        else:
            sr = st.selectbox("Recept:", list(rd.keys()), key="mix_recept")
            vo = st.number_input("Objem vody (litry):", min_value=1, step=100, value=1000)
            da = st.date_input("Datum míchání:", value=date.today(), key="mix_datum")

            if st.button("💧 Uložit míchání", type="primary", use_container_width=True):
                ukaz_potvrzeni(rd[sr], sr, da, vo, uid)

        # Historie posledních míchání
        st.markdown("---")
        st.markdown("##### Poslední míchání")
        hist_m = execute_query(
            "SELECT m.datum, r.nazev, m.objem_vody_l, COALESCE(u.cele_jmeno, u.username) "
            "FROM michani m "
            "JOIN recept r ON m.recept_id=r.id "
            "LEFT JOIN users u ON m.user_id=u.id "
            "WHERE r.stredisko_id=%s "
            "ORDER BY m.datum DESC, m.id DESC LIMIT 10",
            (st.session_state['stredisko_id'],), fetch=True
        )
        if hist_m:
            df_m = pd.DataFrame(hist_m, columns=["Datum", "Recept", "Voda (l)", "Míchal"])
            df_m["Datum"] = pd.to_datetime(df_m["Datum"]).dt.strftime("%d.%m.%Y")
            st.dataframe(df_m, use_container_width=True, hide_index=True)
        else:
            st.caption("Zatím žádné záznamy.")

    # ── TAB 2: SKLAD ───────────────────────────────────────────
    with t2:
        mod = st.radio(
            "Režim:",
            ["📋 Inventura", "🚚 Příjem zboží"],
            horizontal=True,
            label_visibility="collapsed"
        )

        # ── Inventura ──────────────────────────────────────────
        if mod == "📋 Inventura":
            st.subheader("Hromadná inventura")
            idat = st.date_input("Datum inventury:", value=date.today())
            st.markdown("---")

            hdata = execute_query(
                "SELECT id, nazev, jednotka FROM hnojivo "
                "WHERE stredisko_id=%s "
                "ORDER BY COALESCE(poradi, 999) ASC, nazev ASC",
                (st.session_state['stredisko_id'],), fetch=True
            )

            if not hdata:
                st.warning("⚠ Žádná hnojiva pro toto středisko.")
            else:
                with st.form("inv_form"):
                    inputy = {}
                    for hid, hnaz, hjed in hdata:
                        c_txt, c_inp = st.columns([2, 1])
                        with c_txt:
                            st.markdown(f"<div class='row-label'>{hnaz}</div>", unsafe_allow_html=True)
                            st.markdown(f"<span class='unit-label'>{hjed}</span>", unsafe_allow_html=True)
                        with c_inp:
                            val = st.number_input(
                                "Množství", key=f"i_{hid}",
                                min_value=0.0, step=10.0,
                                value=None,
                                label_visibility="collapsed",
                                placeholder="—"
                            )
                            inputy[hid] = val
                        st.divider()

                    if st.form_submit_button("💾 Uložit inventuru", type="primary", use_container_width=True):
                        cnt = sum(
                            1 for hid, val in inputy.items()
                            if val is not None and execute_query(
                                "INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) "
                                "VALUES (%s,%s,%s,'inventura')",
                                (hid, idat, val)
                            )
                        )
                        if cnt > 0:
                            st.toast(f"✅ Uloženo {cnt} položek!", icon="📋")
                            st.rerun()
                        else:
                            st.warning("Nic nebylo vyplněno.")

        # ── Příjem ─────────────────────────────────────────────
        else:
            st.subheader("Příjem zboží")
            hd_raw = execute_query(
                "SELECT id, nazev FROM hnojivo WHERE stredisko_id=%s ORDER BY nazev",
                (st.session_state['stredisko_id'],), fetch=True
            )
            if not hd_raw:
                st.warning("⚠ Žádná hnojiva.")
            else:
                hd_dict = {h[1]: h[0] for h in hd_raw}
                sh = st.selectbox("Hnojivo:", list(hd_dict.keys()))
                mn = st.number_input("Množství (+):", min_value=0.01, step=50.0)
                dt = st.date_input("Datum:", value=date.today())
                if st.button("🚚 Uložit příjem", type="primary", use_container_width=True):
                    execute_query(
                        "INSERT INTO dodavky_inventura (hnojivo_id, datum, mnozstvi_kg_l, typ) "
                        "VALUES (%s,%s,%s,'dodavka')",
                        (hd_dict[sh], dt, mn)
                    )
                    st.toast("✅ Příjem uložen!", icon="🚚")
                    st.rerun()

        # ── Admin: řazení hnojiv ───────────────────────────────
        if st.session_state.get('role') == 'admin':
            st.markdown("---")
            with st.expander("⚙️ Pořadí hnojiv (admin)"):
                st.caption("Nižší číslo = výše v seznamu. 0 = podle abecedy.")
                adh = execute_query(
                    "SELECT id, nazev, COALESCE(poradi, 0) FROM hnojivo "
                    "WHERE stredisko_id=%s ORDER BY poradi ASC, nazev ASC",
                    (st.session_state['stredisko_id'],), fetch=True
                )
                if adh:
                    with st.form("sort_form"):
                        sort_map = {}
                        for ahid, ahnaz, ahpor in adh:
                            ac1, ac2 = st.columns([3, 1])
                            ac1.write(f"**{ahnaz}**")
                            new_p = ac2.number_input(
                                "Pořadí", value=int(ahpor), min_value=0, step=1,
                                key=f"sort_{ahid}", label_visibility="collapsed"
                            )
                            sort_map[ahid] = new_p
                        if st.form_submit_button("✅ Uložit pořadí"):
                            for shid, sval in sort_map.items():
                                execute_query("UPDATE hnojivo SET poradi=%s WHERE id=%s", (sval, shid))
                            st.toast("🔄 Pořadí aktualizováno!")
                            st.rerun()

        # ── Historie ───────────────────────────────────────────
        st.markdown("---")
        st.markdown("##### Poslední pohyby")
        hist = execute_query(
            "SELECT di.datum, h.nazev, di.mnozstvi_kg_l, di.typ "
            "FROM dodavky_inventura di "
            "JOIN hnojivo h ON di.hnojivo_id=h.id "
            "WHERE h.stredisko_id=%s "
            "ORDER BY di.id DESC LIMIT 8",
            (st.session_state['stredisko_id'],), fetch=True
        )
        if hist:
            for r in hist:
                icon = "📝" if r[3] == 'inventura' else "🚚"
                st.text(f"{icon}  {format_date(r[0])}  |  {r[1]}:  {format_num(r[2])}")
        else:
            st.caption("Zatím žádné záznamy.")

    # ── TAB 3: RECEPTY ─────────────────────────────────────────
    with t3:
        st.subheader("Složení receptů")
        if not rd:
            st.warning("⚠ Žádné recepty pro toto středisko.")
        else:
            rv = st.selectbox("Recept:", list(rd.keys()), key="view_recept")
            its = execute_query(
                "SELECT rp.tank, h.nazev, rp.mnozstvi_na_1000l, h.jednotka "
                "FROM recept_polozka rp "
                "JOIN hnojivo h ON rp.hnojivo_id=h.id "
                "WHERE rp.recept_id=%s "
                "ORDER BY rp.tank, rp.poradi ASC, h.nazev",
                (rd[rv],), fetch=True
            )
            if its:
                rows_a = [{"Hnojivo": i[1], "1 000 l": format_num(i[2]), "J.": i[3]} for i in its if i[0] == 'A']
                rows_b = [{"Hnojivo": i[1], "1 000 l": format_num(i[2]), "J.": i[3]} for i in its if i[0] == 'B']

                ca, cb = st.columns(2)
                with ca:
                    st.markdown("**🔵 TANK A**")
                    if rows_a:
                        st.dataframe(pd.DataFrame(rows_a), use_container_width=True, hide_index=True)
                    else:
                        st.caption("Prázdný tank")
                with cb:
                    st.markdown("**🟢 TANK B**")
                    if rows_b:
                        st.dataframe(pd.DataFrame(rows_b), use_container_width=True, hide_index=True)
                    else:
                        st.caption("Prázdný tank")

                # Součet pro různé objemy
                st.markdown("---")
                st.markdown("##### Přepočet na objemy")
                objemy = [500, 1000, 2000, 3000, 5000]
                for tank_label, tank_key in [("🔵 Tank A", "A"), ("🟢 Tank B", "B")]:
                    tank_items = [(i[1], float(i[2]), i[3]) for i in its if i[0] == tank_key]
                    if tank_items:
                        st.markdown(f"**{tank_label}**")
                        cols = st.columns([2] + [1] * len(objemy))
                        cols[0].markdown("*Hnojivo*")
                        for j, obj in enumerate(objemy):
                            cols[j+1].markdown(f"*{obj} l*")
                        for nazev, mnoz, jed in tank_items:
                            cols = st.columns([2] + [1] * len(objemy))
                            cols[0].write(nazev)
                            for j, obj in enumerate(objemy):
                                cols[j+1].write(format_num(mnoz * obj / 1000) + f" {jed}")
            else:
                st.info("Recept nemá žádné položky.")

    # ── TAB 4: BILANCE ─────────────────────────────────────────
    with t4:
        st.subheader("Měsíční bilance")

        bcol1, bcol2 = st.columns(2)
        mesic = bcol1.selectbox(
            "Měsíc:", list(range(1, 13)),
            index=date.today().month - 1,
            format_func=lambda m: date(2000, m, 1).strftime("%B")
        )
        rok = bcol2.selectbox(
            "Rok:", list(range(2024, 2036)),
            index=date.today().year - 2024
        )

        if st.button("Vypočítat bilanci", type="primary"):
            start_date = date(rok, mesic, 1)
            end_date = date(rok + 1, 1, 1) if mesic == 12 else date(rok, mesic + 1, 1)

            hn = execute_query(
                "SELECT id, nazev, jednotka FROM hnojivo "
                "WHERE stredisko_id=%s ORDER BY COALESCE(poradi,999), nazev",
                (st.session_state['stredisko_id'],), fetch=True
            ) or []

            rows = []
            for hid, hna, hje in hn:
                # Poslední inventura <= začátek měsíce
                li = execute_query(
                    "SELECT mnozstvi_kg_l, datum FROM dodavky_inventura "
                    "WHERE hnojivo_id=%s AND typ='inventura' AND datum<=%s "
                    "ORDER BY datum DESC, id DESC LIMIT 1",
                    (hid, start_date), fetch=True
                )
                istav, idat = (float(li[0][0]), li[0][1]) if li else (0.0, date(2000, 1, 1))

                ed = execute_query(
                    "SELECT COALESCE(SUM(mnozstvi_kg_l),0) FROM dodavky_inventura "
                    "WHERE hnojivo_id=%s AND typ='dodavka' AND datum>%s AND datum<%s",
                    (hid, idat, start_date), fetch=True
                )[0][0]
                es = execute_query(
                    "SELECT COALESCE(SUM(m.objem_vody_l * rp.mnozstvi_na_1000l / 1000.0),0) "
                    "FROM michani m JOIN recept_polozka rp ON m.recept_id=rp.recept_id "
                    "WHERE rp.hnojivo_id=%s AND m.datum>%s AND m.datum<%s",
                    (hid, idat, start_date), fetch=True
                )[0][0]
                p_stav = istav + float(ed) - float(es)

                md = execute_query(
                    "SELECT COALESCE(SUM(mnozstvi_kg_l),0) FROM dodavky_inventura "
                    "WHERE hnojivo_id=%s AND typ='dodavka' AND datum>=%s AND datum<%s",
                    (hid, start_date, end_date), fetch=True
                )[0][0]
                ms = execute_query(
                    "SELECT COALESCE(SUM(m.objem_vody_l * rp.mnozstvi_na_1000l / 1000.0),0) "
                    "FROM michani m JOIN recept_polozka rp ON m.recept_id=rp.recept_id "
                    "WHERE rp.hnojivo_id=%s AND m.datum>=%s AND m.datum<%s",
                    (hid, start_date, end_date), fetch=True
                )[0][0]

                vd, vs = float(md), float(ms)
                kz = p_stav + vd - vs

                if abs(p_stav) > 0.001 or vd > 0 or vs > 0:
                    rows.append({
                        "Hnojivo": hna,
                        "J.": hje,
                        "Stav začátek": format_num(p_stav),
                        "Příjem": format_num(vd),
                        "Výdej": format_num(vs),
                        "Stav konec": format_num(kz),
                    })

            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("Pro vybrané období nejsou žádná data.")
