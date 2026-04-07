import streamlit as st
import psycopg2
import psycopg2.pool
import pandas as pd
from datetime import date
import locale
import hashlib

# --- NASTAVENÍ ČEŠTINY ---
try:
    locale.setlocale(locale.LC_ALL, "cs_CZ.UTF-8")
except:
    try:
        locale.setlocale(locale.LC_ALL, "Czech_Czech Republic.1250")
    except:
        pass

# --- 1. KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Sklad Hnojiv", page_icon="🌱", layout="centered")

# --- 2. CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0f1117; color: #e2e8f0; }
    h1, h2, h3, h4, h5 { color: #00c896 !important; font-family: 'Segoe UI', sans-serif; }

    div.stButton > button {
        background-color: #1c2230; color: #e2e8f0;
        border: 1px solid #2d3748; border-radius: 8px;
        font-weight: 600; padding: 0.45rem 1rem;
        transition: all 0.15s ease;
    }
    div.stButton > button:hover {
        background-color: #2d3748; border-color: #00c896; color: #00c896;
    }
    div.stButton > button[kind="primary"] {
        background-color: #00c896; color: #000; border: none; font-weight: 700;
    }
    div.stButton > button[kind="primary"]:hover { background-color: #009e78; }

    .stNumberInput input, .stTextInput input {
        background-color: #1e2533 !important; color: #e2e8f0 !important;
        border-radius: 7px !important; border: 1px solid #2d3748 !important;
    }
    .stSelectbox > div > div {
        background-color: #1e2533 !important; color: #e2e8f0 !important;
        border: 1px solid #2d3748 !important; border-radius: 7px !important;
    }
    .stDateInput input {
        background-color: #1e2533 !important; color: #e2e8f0 !important;
        border: 1px solid #2d3748 !important;
    }
    .stDataFrame, .stTable { border-radius: 8px; overflow: hidden; }
    thead tr th {
        background-color: #0f1117 !important; color: #94a3b8 !important;
        font-size: 0.85rem !important;
    }
    tbody tr td { background-color: #161b22 !important; color: #e2e8f0 !important; }
    tbody tr:nth-child(odd) td { background-color: #1c2230 !important; }

    hr { margin: 0.6rem 0; border-color: #2d3748; }
    .row-label { font-size: 1.05rem; font-weight: 600; padding-top: 8px; color: #e2e8f0; }
    .unit-label { color: #94a3b8; font-size: 0.88rem; }

    div[data-testid="stInfo"] {
        background-color: #1c2230; border-left: 3px solid #00c896; color: #e2e8f0;
    }
    div[data-testid="stToast"] {
        background-color: #1c2230; border: 1px solid #00c896; color: #e2e8f0;
    }
    .stTabs [data-baseweb="tab-list"] {
        background-color: #0f1117; border-bottom: 1px solid #2d3748;
    }
    .stTabs [data-baseweb="tab"] { color: #94a3b8; font-weight: 600; }
    .stTabs [aria-selected="true"] {
        color: #00c896 !important; border-bottom: 2px solid #00c896 !important;
    }
    .stRadio > div { gap: 1rem; }
    details { border: 1px solid #2d3748 !important; border-radius: 8px !important; }
    summary { color: #94a3b8 !important; }

    /* Přepočtová tabulka */
    .prepocet-table {
        width: 100%; border-collapse: collapse;
        font-size: 0.9rem; margin-bottom: 1.2rem;
    }
    .prepocet-table th {
        background-color: #0f1117; color: #94a3b8;
        padding: 7px 12px; text-align: right; font-weight: 600;
        border-bottom: 2px solid #2d3748;
    }
    .prepocet-table th:first-child { text-align: left; min-width: 160px; }
    .prepocet-table td {
        background-color: #161b22; color: #e2e8f0;
        padding: 6px 12px; text-align: right;
        border-bottom: 1px solid #2d3748;
    }
    .prepocet-table td:first-child { text-align: left; font-weight: 500; }
    .prepocet-table tr:nth-child(odd) td { background-color: #1c2230; }
    .prepocet-table tr:hover td { background-color: #1e3a5f !important; }
    .tank-label {
        font-size: 0.95rem; font-weight: 700;
        margin: 1rem 0 0.4rem 0; color: #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# 3. HASHOVÁNÍ HESEL — stejná implementace jako desktop app
# ═══════════════════════════════════════════════════════════════
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(plain: str, stored: str):
    """Vrátí (ok: bool, needs_upgrade: bool)."""
    if hash_password(plain) == stored:
        return True, False          # Hashované heslo — OK
    if plain == stored:
        return True, True           # Plain-text — OK, ale upgradujeme
    return False, False

# ═══════════════════════════════════════════════════════════════
# 4. DB — CONNECTION POOL
# Klíčová oprava výkonu č. 1:
# Dříve: psycopg2.connect() = nové TCP spojení při každém dotazu (~100–300 ms)
# Nyní:  ThreadedConnectionPool = sdílené spojení, zapůjčujeme na dobu dotazu
# ═══════════════════════════════════════════════════════════════
@st.cache_resource
def get_pool():
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1, maxconn=5,
        **st.secrets["postgres"]
    )

def execute_query(query, params=None, fetch=False):
    pool = get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()
                conn.commit()
                return result
            conn.commit()
            return True
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        st.error(f"Chyba DB: {e}")
        return None
    finally:
        pool.putconn(conn)   # Vždy vrátit zpět do poolu

# ═══════════════════════════════════════════════════════════════
# 5. INICIALIZACE DB — jednou za životnost serveru
# Klíčová oprava výkonu č. 2:
# Dříve: check_db_structure() bez cache = 6× ALTER TABLE při KAŽDÉM rerunu
#        (každý klik spouštěl ALTER TABLE = stovky zbytečných DB dotazů)
# Nyní:  @st.cache_resource = spustí se jednou, výsledek se kešuje
# ═══════════════════════════════════════════════════════════════
@st.cache_resource
def init_db_once():
    opravy = [
        "ALTER TABLE hnojivo ADD COLUMN IF NOT EXISTS poradi INTEGER DEFAULT 0",
        "ALTER TABLE michani ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS cele_jmeno VARCHAR(150)",
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
    return True

init_db_once()

# ═══════════════════════════════════════════════════════════════
# 6. POMOCNÉ FUNKCE
# ═══════════════════════════════════════════════════════════════
def format_num(val):
    if val is None:
        return ""
    try:
        return f"{float(val):g}".replace(".", ",")
    except:
        return str(val)

def format_date(d):
    if d is None:
        return ""
    try:
        return d.strftime("%d.%m.%Y")
    except:
        return str(d)

# ═══════════════════════════════════════════════════════════════
# 7. VÝKONNÉ DB FUNKCE
# ═══════════════════════════════════════════════════════════════
def vypocti_bilanci(stredisko_id: int, start_date: date, end_date: date) -> list:
    """
    Klíčová oprava výkonu č. 3:
    Dříve: Pythonská smyčka N hnojiv × 4 dotazy = 80 dotazů pro 20 hnojiv
    Nyní:  1 agregační SQL dotaz s CTE — výsledek stejný, rychlost 20–50×
    """
    sql = """
    WITH hnojiva AS (
        SELECT id, nazev, jednotka
        FROM hnojivo
        WHERE stredisko_id = %(sid)s
        ORDER BY COALESCE(poradi, 999), nazev
    ),
    posl_inv AS (
        SELECT DISTINCT ON (di.hnojivo_id)
            di.hnojivo_id,
            di.mnozstvi_kg_l AS inv_stav,
            di.datum         AS inv_datum
        FROM dodavky_inventura di
        WHERE di.typ = 'inventura'
          AND di.datum <= %(start)s
          AND di.hnojivo_id IN (SELECT id FROM hnojiva)
        ORDER BY di.hnojivo_id, di.datum DESC, di.id DESC
    ),
    pocatecni AS (
        SELECT
            h.id,
            COALESCE(pi.inv_stav, 0)
            + COALESCE((
                SELECT SUM(di.mnozstvi_kg_l)
                FROM dodavky_inventura di
                WHERE di.hnojivo_id = h.id
                  AND di.typ = 'dodavka'
                  AND di.datum > COALESCE(pi.inv_datum, '2000-01-01'::date)
                  AND di.datum < %(start)s
            ), 0)
            - COALESCE((
                SELECT SUM(m.objem_vody_l * rp.mnozstvi_na_1000l / 1000.0)
                FROM michani m
                JOIN recept_polozka rp ON m.recept_id = rp.recept_id
                WHERE rp.hnojivo_id = h.id
                  AND m.datum > COALESCE(pi.inv_datum, '2000-01-01'::date)
                  AND m.datum < %(start)s
            ), 0) AS p_stav
        FROM hnojiva h
        LEFT JOIN posl_inv pi ON pi.hnojivo_id = h.id
    ),
    prijem AS (
        SELECT hnojivo_id, COALESCE(SUM(mnozstvi_kg_l), 0) AS castka
        FROM dodavky_inventura
        WHERE typ = 'dodavka'
          AND datum >= %(start)s AND datum < %(end)s
          AND hnojivo_id IN (SELECT id FROM hnojiva)
        GROUP BY hnojivo_id
    ),
    spotreba AS (
        SELECT rp.hnojivo_id,
               COALESCE(SUM(m.objem_vody_l * rp.mnozstvi_na_1000l / 1000.0), 0) AS castka
        FROM michani m
        JOIN recept_polozka rp ON m.recept_id = rp.recept_id
        WHERE m.datum >= %(start)s AND m.datum < %(end)s
          AND rp.hnojivo_id IN (SELECT id FROM hnojiva)
        GROUP BY rp.hnojivo_id
    )
    SELECT
        h.nazev, h.jednotka,
        pc.p_stav,
        COALESCE(pr.castka, 0) AS prijem,
        COALESCE(sp.castka, 0) AS vydej,
        pc.p_stav + COALESCE(pr.castka, 0) - COALESCE(sp.castka, 0) AS konec
    FROM hnojiva h
    JOIN pocatecni pc ON pc.id = h.id
    LEFT JOIN prijem pr ON pr.hnojivo_id = h.id
    LEFT JOIN spotreba sp ON sp.hnojivo_id = h.id
    WHERE ABS(pc.p_stav) > 0.001
       OR COALESCE(pr.castka, 0) > 0
       OR COALESCE(sp.castka, 0) > 0
    ORDER BY h.nazev
    """
    rows = execute_query(sql, {"sid": stredisko_id, "start": start_date, "end": end_date}, fetch=True)
    if not rows:
        return []
    return [
        {
            "Hnojivo": r[0], "J.": r[1],
            "Stav začátek": format_num(r[2]),
            "Příjem": format_num(r[3]),
            "Výdej": format_num(r[4]),
            "Stav konec": format_num(r[5]),
        }
        for r in rows
    ]

def prepocet_tabulka_html(items: list, tank_label: str, tank_key: str, objemy: list) -> str:
    """
    HTML přepočtová tabulka — čistý Python, žádné DB dotazy.
    Objemy jsou v litrech.
    """
    tank_items = [(i[1], float(i[2]), i[3]) for i in items if i[0] == tank_key]
    if not tank_items:
        return ""

    header_cols = "".join(
        f"<th>{obj:,} l</th>".replace(",", "\u202f")   # úzká mezera jako oddělovač tisíců
        for obj in objemy
    )
    rows_html = ""
    for nazev, mnoz, jed in tank_items:
        cells = "".join(
            f"<td>{format_num(mnoz * obj / 1000)} {jed}</td>"
            for obj in objemy
        )
        rows_html += f"<tr><td>{nazev}</td>{cells}</tr>"

    return (
        f"<p class='tank-label'>{tank_label}</p>"
        f"<table class='prepocet-table'>"
        f"<thead><tr><th>Hnojivo</th>{header_cols}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>"
    )

# ═══════════════════════════════════════════════════════════════
# 8. SESSION STATE + ZAPAMATOVÁNÍ (cookies)
# ═══════════════════════════════════════════════════════════════
# Inicializace session state
for k, v in {
    'logged_in': False, 'user_id': None, 'role': None,
    'display_name': None, 'stredisko_id': None, 'stredisko_name': None,
    'mix_saved': False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# CookieManager — MUSÍ být inicializován vždy na začátku,
# ne uvnitř if bloků. Streamlit jinak nenačte jeho JS.
try:
    from streamlit_cookies_manager import EncryptedCookieManager
    cookies = EncryptedCookieManager(
        prefix="sklad_",
        password=st.secrets.get("cookie_password", "sklad-hnojiv-default-key-2024")
    )
    if not cookies.ready():
        st.stop()
    COOKIES_OK = True
except Exception:
    cookies = None
    COOKIES_OK = False

def get_cookie(name, default=''):
    if not COOKIES_OK or cookies is None:
        return default
    try:
        return cookies.get(name) or default
    except Exception:
        return default

def set_cookie(name, value):
    if not COOKIES_OK or cookies is None:
        return
    try:
        cookies[name] = value
        cookies.save()
    except Exception:
        pass

def del_cookie(name):
    if not COOKIES_OK or cookies is None:
        return
    try:
        if name in cookies:
            del cookies[name]
            cookies.save()
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# A) LOGIN
# ═══════════════════════════════════════════════════════════════
if not st.session_state['logged_in']:

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("## 🌱 Sklad Hnojiv")
        st.markdown("##### Přihlášení")
        st.markdown("---")

        strediska = execute_query(
            "SELECT id, nazev FROM stredisko ORDER BY nazev", fetch=True
        )
        sd = {r[1]: r[0] for r in strediska} if strediska else {}
        if not sd:
            st.error("⚠ Nelze načíst střediska.")
            st.stop()

        names = list(sd.keys())
        saved_s = get_cookie('s')
        saved_u = get_cookie('u')
        s_index = names.index(saved_s) if saved_s in names else 0

        with st.form("login_form"):
            s_name = st.selectbox("Středisko", names, index=s_index)
            u = st.text_input(
                "Přihlašovací jméno",
                value=saved_u
            )
            p = st.text_input("Heslo", type="password")
            zapamatovat = st.checkbox(
                "Zapamatovat jméno a středisko",
                value=bool(saved_s or saved_u),
            )
            submit = st.form_submit_button(
                "Přihlásit se",
                type="primary",
                use_container_width=True
            )

        if submit:
            if not u or not p:
                st.error("Zadejte jméno i heslo.")
            else:
                ud = execute_query(
                    "SELECT id, role, cele_jmeno, password FROM users "
                    "WHERE username=%s AND stredisko_id=%s",
                    (u.strip(), sd[s_name]), fetch=True
                )
                if ud:
                    uid, role, cele_jmeno, stored_pw = ud[0]
                    ok, needs_upgrade = verify_password(p, stored_pw)
                    if ok:
                        if needs_upgrade:
                            execute_query(
                                "UPDATE users SET password=%s WHERE id=%s",
                                (hash_password(p), uid)
                            )
                        if zapamatovat:
                            set_cookie('s', s_name)
                            set_cookie('u', u.strip())
                        else:
                            del_cookie('s')
                            del_cookie('u')
                        st.session_state.update({
                            'logged_in': True,
                            'user_id': uid,
                            'role': role,
                            'display_name': cele_jmeno if cele_jmeno else u.strip(),
                            'stredisko_id': sd[s_name],
                            'stredisko_name': s_name,
                        })
                        st.rerun()
                    else:
                        st.error("❌ Špatné heslo.")
                else:
                    st.error("❌ Uživatel nenalezen nebo špatné středisko.")

# ═══════════════════════════════════════════════════════════════
# B) HLAVNÍ OBSAH
# ═══════════════════════════════════════════════════════════════
else:
    sid = st.session_state['stredisko_id']

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

    # Recepty načteme jednou — sdílené mezi taby
    recs_raw = execute_query(
        "SELECT id, nazev FROM recept WHERE stredisko_id=%s ORDER BY nazev",
        (sid,), fetch=True
    ) or []
    rd = {r[1]: r[0] for r in recs_raw}

    # Dialog potvrzení míchání
    @st.dialog("Potvrzení míchání")
    def ukaz_potvrzeni(recept_id, recept_nazev, datum, objem_vody, user_id):
        st.write(f"**Recept:** {recept_nazev}")
        st.write(f"**Voda:** {objem_vody:,} litrů")
        st.write(f"**Datum:** {format_date(datum)}")
        st.write("")
        c_ano, c_ne = st.columns(2)
        if c_ano.button("✅ Potvrdit", type="primary", use_container_width=True):
            res = execute_query(
                "INSERT INTO michani (recept_id, datum, objem_vody_l, user_id) "
                "VALUES (%s,%s,%s,%s)",
                (recept_id, datum, objem_vody, user_id)
            )
            if res:
                st.session_state['mix_saved'] = True
            st.rerun()
        if c_ne.button("❌ Storno", use_container_width=True):
            st.rerun()

    if st.session_state.get('mix_saved'):
        st.toast("✅ Míchání bylo uloženo!", icon="💧")
        st.session_state['mix_saved'] = False

    # ── TABY — Bilance jen pro admina ──────────────────────────
    is_admin = st.session_state.get('role') == 'admin'

    tab_labels = ["💧 Míchání", "📦 Sklad", "🧪 Recepty"]
    if is_admin:
        tab_labels.append("📊 Bilance")

    tabs = st.tabs(tab_labels)
    t1 = tabs[0]
    t2 = tabs[1]
    t3 = tabs[2]
    t4 = tabs[3] if is_admin else None

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

        st.markdown("---")
        st.markdown("##### Poslední míchání")
        hist_m = execute_query(
            "SELECT m.datum, r.nazev, m.objem_vody_l, "
            "COALESCE(u.cele_jmeno, u.username, 'Neznámý') "
            "FROM michani m "
            "JOIN recept r ON m.recept_id=r.id "
            "LEFT JOIN users u ON m.user_id=u.id "
            "WHERE r.stredisko_id=%s "
            "ORDER BY m.datum DESC, m.id DESC LIMIT 10",
            (sid,), fetch=True
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
            "Režim:", ["📋 Inventura", "🚚 Příjem zboží"],
            horizontal=True, label_visibility="collapsed"
        )

        if mod == "📋 Inventura":
            st.subheader("Hromadná inventura")
            idat = st.date_input("Datum inventury:", value=date.today())
            st.markdown("---")

            hdata = execute_query(
                "SELECT id, nazev, jednotka FROM hnojivo "
                "WHERE stredisko_id=%s "
                "ORDER BY COALESCE(poradi, 999) ASC, nazev ASC",
                (sid,), fetch=True
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
                            inputy[hid] = st.number_input(
                                "Množství", key=f"i_{hid}",
                                min_value=0.0, step=10.0, value=None,
                                label_visibility="collapsed", placeholder="—"
                            )
                        st.divider()

                    if st.form_submit_button("💾 Uložit inventuru", type="primary", use_container_width=True):
                        cnt = 0
                        for hid, val in inputy.items():
                            if val is not None:
                                execute_query(
                                    "INSERT INTO dodavky_inventura "
                                    "(hnojivo_id, datum, mnozstvi_kg_l, typ) "
                                    "VALUES (%s,%s,%s,'inventura')",
                                    (hid, idat, val)
                                )
                                cnt += 1
                        if cnt > 0:
                            st.toast(f"✅ Uloženo {cnt} položek!", icon="📋")
                            st.rerun()
                        else:
                            st.warning("Nic nebylo vyplněno.")
        else:
            st.subheader("Příjem zboží")
            hd_raw = execute_query(
                "SELECT id, nazev FROM hnojivo WHERE stredisko_id=%s ORDER BY nazev",
                (sid,), fetch=True
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
                        "INSERT INTO dodavky_inventura "
                        "(hnojivo_id, datum, mnozstvi_kg_l, typ) "
                        "VALUES (%s,%s,%s,'dodavka')",
                        (hd_dict[sh], dt, mn)
                    )
                    st.toast("✅ Příjem uložen!", icon="🚚")
                    st.rerun()

        if st.session_state.get('role') == 'admin':
            st.markdown("---")
            with st.expander("⚙️ Pořadí hnojiv (admin)"):
                st.caption("Nižší číslo = výše v seznamu. 0 = abeceda.")
                adh = execute_query(
                    "SELECT id, nazev, COALESCE(poradi, 0) FROM hnojivo "
                    "WHERE stredisko_id=%s ORDER BY poradi ASC, nazev ASC",
                    (sid,), fetch=True
                )
                if adh:
                    with st.form("sort_form"):
                        sort_map = {}
                        for ahid, ahnaz, ahpor in adh:
                            ac1, ac2 = st.columns([3, 1])
                            ac1.write(f"**{ahnaz}**")
                            sort_map[ahid] = ac2.number_input(
                                "Pořadí", value=int(ahpor), min_value=0, step=1,
                                key=f"sort_{ahid}", label_visibility="collapsed"
                            )
                        if st.form_submit_button("✅ Uložit pořadí"):
                            for shid, sval in sort_map.items():
                                execute_query("UPDATE hnojivo SET poradi=%s WHERE id=%s", (sval, shid))
                            st.toast("🔄 Pořadí aktualizováno!")
                            st.rerun()

        st.markdown("---")
        st.markdown("##### Poslední pohyby")
        hist = execute_query(
            "SELECT di.datum, h.nazev, di.mnozstvi_kg_l, di.typ "
            "FROM dodavky_inventura di "
            "JOIN hnojivo h ON di.hnojivo_id=h.id "
            "WHERE h.stredisko_id=%s "
            "ORDER BY di.id DESC LIMIT 8",
            (sid,), fetch=True
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
                # Základní složení na 1000 l
                rows_a = [{"Hnojivo": i[1], "1 000 l": format_num(i[2]), "J.": i[3]}
                          for i in its if i[0] == 'A']
                rows_b = [{"Hnojivo": i[1], "1 000 l": format_num(i[2]), "J.": i[3]}
                          for i in its if i[0] == 'B']

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

                # Přepočtová tabulka 1000–5000 l
                st.markdown("---")
                st.markdown("##### Přepočet množství")

                OBJEMY = [1000, 2000, 3000, 4000, 5000]
                html_a = prepocet_tabulka_html(its, "🔵 Tank A", "A", OBJEMY)
                html_b = prepocet_tabulka_html(its, "🟢 Tank B", "B", OBJEMY)
                st.markdown(html_a + html_b, unsafe_allow_html=True)

            else:
                st.info("Recept nemá žádné položky.")

    # ── TAB 4: BILANCE — pouze admin ───────────────────────────
    if is_admin and t4 is not None:
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
                index=max(0, date.today().year - 2024)
            )

            if st.button("📊 Vypočítat bilanci", type="primary", use_container_width=True):
                start_date = date(rok, mesic, 1)
                end_date = date(rok + 1, 1, 1) if mesic == 12 else date(rok, mesic + 1, 1)

                with st.spinner("Počítám bilanci…"):
                    rows = vypocti_bilanci(sid, start_date, end_date)

                if rows:
                    st.markdown(
                        f"**{date(2000, mesic, 1).strftime('%B')} {rok}** "
                        f"· {len(rows)} hnojiv"
                    )
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.info("Pro vybrané období nejsou žádná data.")
