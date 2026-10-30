import pandas as pd
import json
import time
import re
import hashlib
from pathlib import Path
from db_manager import DBManager
import export_in_progress
import portal_adapter
from demo_core import NOT_DEMO
import logging

logger = logging.getLogger("EngineCore")

BASE_DIR = Path(__file__).parent / "output"
NEW_FILE_DEFAULT = BASE_DIR / "in_progress_tenders.xlsx"
db_default = DBManager()


def normalize_arabic(text: str) -> str:
    """
    Normalizes Arabic text to handle minor spelling differences.
    Strips Tashkeel, unifies Hamza forms, and trims whitespace.
    This prevents false 'new tender' detections due to encoding differences.
    """
    if not isinstance(text, str):
        return str(text)
    # Unify all Alef variants to plain Alef
    text = re.sub(r'[أإآ]', 'ا', text)
    # Remove Tashkeel (diacritics)
    text = re.sub(r'[\u064B-\u065F]', '', text)
    # Remove Tatweel
    text = text.replace('ـ', '')
    return text.strip()

def clean_cell(value, default="N/A") -> str:
    if pd.isna(value):
        return default
    text = str(value).strip()
    if text.lower() in ("", "nan", "n/a", "none", "nat"):
        return default
    return text

def is_valid_tender_id(value) -> bool:
    text = clean_cell(value, default="")
    return bool(text)

def build_tender_identity(row) -> str:
    raw_id = clean_cell(row.get('رقم المنافسة', ''), default="")
    if raw_id:
        return raw_id

    title = normalize_arabic(clean_cell(row.get('اسم المنافسة', ''), default=""))
    owner = normalize_arabic(clean_cell(row.get('المالك', ''), default=""))
    business_type = normalize_arabic(clean_cell(row.get('نوع الأعمال', ''), default=""))
    sector = normalize_arabic(clean_cell(row.get('القطاع', ''), default=""))
    identity_text = "|".join([title, owner, business_type, sector])
    digest = hashlib.sha1(identity_text.encode("utf-8")).hexdigest()[:16]
    return f"AUTO-{digest}"

# ── Soft identity matching ────────────────────────────────────────────
# رقم المنافسة فارغ في تصدير المنصة، فالمفتاح AUTO-* مشتق من الاسم/المالك/النوع/القطاع.
# أي تعديل بسيط في هذه الحقول يغيّر المفتاح فتظهر المنافسة كـ"مغلقة + جديدة".
# المطابقة هنا محافظة عمداً: منافسات مختلفة فعلاً عناوينها متشابهة جداً
# (الجزء الأول/الثاني، الشمالية/الجنوبية، أحياء مختلفة) ويجب ألا تندمج.

SOFT_MATCH_MIN_RATIO = 0.90        # تشابه العنوان كاملاً (بعد التطبيع وحذف المسافات)
SOFT_MATCH_TOKEN_RATIO = 0.75      # كل كلمة تغيّرت يجب أن تكون تصحيحاً إملائياً لكلمة مقابلة
SOFT_MATCH_CLOSED_DAYS = 30        # نافذة ربط منافسة مغلقة حديثاً بصيغتها الجديدة

# كلمات تميّز منافسة عن أخرى — أي اختلاف فيها يعني منافسة مختلفة
DISTINGUISHING_TOKENS = {
    "الاول", "الاولي", "الثاني", "الثانيه", "الثالث", "الثالثه", "الرابع", "الرابعه",
    "الخامس", "الخامسه", "السادس", "السادسه", "السابع", "السابعه", "الثامن", "الثامنه",
    "التاسع", "التاسعه", "العاشر", "العاشره", "اول", "ثاني", "ثالث", "رابع", "خامس",
    "شمال", "جنوب", "شرق", "غرب", "وسط", "الشمال", "الجنوب", "الشرق", "الغرب", "الوسط",
    "الشماليه", "الجنوبيه", "الشرقيه", "الغربيه", "الوسطي", "شمالي", "جنوبي", "شرقي", "غربي",
    "المرحله", "الحزمه", "الجزء", "القطاع", "المنطقه", "المجموعه", "العقد", "الدفعه",
}


def strong_normalize(text) -> str:
    """تطبيع أقوى للمقارنة فقط (لا يُستخدم في المفتاح حتى لا تتغير المفاتيح الحالية)."""
    text = normalize_arabic(clean_cell(text, default="")).lower()
    text = text.replace('ى', 'ي').replace('ة', 'ه').replace('ؤ', 'و').replace('ئ', 'ي')
    text = re.sub(r'[^\w\s]', ' ', text)
    text = text.replace('_', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def titles_match(title_a, title_b) -> bool:
    """هل العنوانان لنفس المنافسة؟ يسمح بتصحيحات إملائية/مسافات فقط."""
    from collections import Counter
    from difflib import SequenceMatcher

    a, b = strong_normalize(title_a), strong_normalize(title_b)
    if not a or not b:
        return False
    if a == b or a.replace(' ', '') == b.replace(' ', ''):
        return True
    if SequenceMatcher(None, a.replace(' ', ''), b.replace(' ', '')).ratio() < SOFT_MATCH_MIN_RATIO:
        return False
    if sorted(re.findall(r'\d+', a)) != sorted(re.findall(r'\d+', b)):
        return False

    ta, tb = Counter(a.split()), Counter(b.split())
    removed, added = list((ta - tb).elements()), list((tb - ta).elements())
    if len(removed) != len(added):
        return False  # كلمة أُضيفت أو حُذفت → قد تكون منافسة مختلفة
    if any(t in DISTINGUISHING_TOKENS for t in removed + added):
        return False
    for old in removed:
        best = max(added, key=lambda new: SequenceMatcher(None, old, new).ratio())
        if SequenceMatcher(None, old, best).ratio() < SOFT_MATCH_TOKEN_RATIO:
            return False
        added.remove(best)
    return True


def find_soft_match(row, candidates):
    """
    يبحث بين منافسات الماستر الغائبة عن المنصة عن نفس المنافسة بصيغة معدّلة.
    يرجع tender_id فقط عند وجود مرشح واحد مؤكد؛ غير ذلك None (تُعامل كجديدة).
    """
    title = clean_cell(row.get('اسم المنافسة', ''), default="")
    owner = strong_normalize(row.get('المالك', ''))
    exact_title = strong_normalize(title)
    matches = []
    for m in candidates:
        m_title = strong_normalize(m.get('title', ''))
        same_owner = owner and owner == strong_normalize(m.get('owner', ''))
        # عنوان مطابق تماماً وطويل بما يكفي → نفس المنافسة حتى لو عُدّل المالك/النوع/القطاع
        if exact_title and exact_title == m_title and len(exact_title) >= 20:
            matches.append(m)
        elif same_owner and titles_match(title, m.get('title', '')):
            matches.append(m)
    return str(matches[0]['tender_id']) if len(matches) == 1 else None


def _ensure_alias_table(conn):
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tender_aliases (
            alias_key  TEXT PRIMARY KEY,
            tender_id  TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def _load_aliases(active_db) -> dict:
    with active_db._get_connection() as conn:
        _ensure_alias_table(conn)
        return {r[0]: r[1] for r in conn.execute("SELECT alias_key, tender_id FROM tender_aliases").fetchall()}


def _is_soft_match_candidate(m_row) -> bool:
    status = str(m_row.get('status') or '')
    if status == 'REJECTED':
        return False
    if status != 'CLOSED':
        return True
    closed_at = pd.to_datetime(m_row.get('updated_at'), errors='coerce')
    return pd.notnull(closed_at) and (pd.Timestamp.now() - closed_at).days <= SOFT_MATCH_CLOSED_DAYS


def _relink_renamed_tenders(active_db, df_new, df_master, master_ids) -> int:
    """
    يربط صفوف المنصة ذات المفاتيح الجديدة بمنافساتها الأصلية في الماستر (إن ثبت أنها نفسها)
    عبر جدول tender_aliases — بدون تغيير tender_id الأصلي (مرتبط بالنتائج والملاحظات والضمانات).
    """
    present = set(df_new['_identity_key'].astype(str))
    candidates = [
        m for m in df_master.to_dict('records')
        if str(m['tender_id']) not in present and _is_soft_match_candidate(m)
    ]
    if not candidates:
        return 0

    relinked = 0
    for idx, row in df_new.iterrows():
        new_key = str(row['_identity_key'])
        if new_key in master_ids:
            continue
        m_id = find_soft_match(row, candidates)
        if not m_id:
            continue
        m_row = next(m for m in candidates if str(m['tender_id']) == m_id)
        candidates.remove(m_row)
        new_title = clean_cell(row.get('اسم المنافسة', ''), default=m_row.get('title'))
        with active_db._get_connection() as conn:
            _ensure_alias_table(conn)
            conn.execute("INSERT OR REPLACE INTO tender_aliases (alias_key, tender_id) VALUES (?, ?)", (new_key, m_id))
            conn.execute(
                "UPDATE master_tenders SET title=?, owner=?, business_type=?, sector=?, "
                "missing_seen_count=0, updated_at=CURRENT_TIMESTAMP WHERE tender_id=?",
                (new_title,
                 clean_cell(row.get('المالك', ''), default=m_row.get('owner')),
                 clean_cell(row.get('نوع الأعمال', ''), default=m_row.get('business_type')),
                 clean_cell(row.get('القطاع', ''), default=m_row.get('sector')),
                 m_id)
            )
            active_db.log_audit(
                "IDENTITY_RELINK", m_id,
                f"Portal edited tender fields: '{m_row.get('title')}' -> '{new_title}' (key {new_key})",
                "SystemScraper", conn=conn
            )
            conn.commit()
        logger.info(f"IDENTITY RELINK: {new_key} -> {m_id} | '{m_row.get('title')}' -> '{new_title}'")
        df_new.at[idx, '_identity_key'] = m_id
        relinked += 1
    return relinked


def _engineer_suggestion(active_db, master_row, owner, business_type, submission_date) -> dict:
    """يُبقي المهندس المكلّف حالياً إن وُجد، وإلا يطلب اقتراحاً ذكياً."""
    suggested_eng = str(master_row.get('assigned_engineer'))
    _NO_ENG = {"nan", "غير محدد", "غير محدد (تهيئة)", "none", "n/a", ""}
    if not suggested_eng or suggested_eng.strip().lower() in _NO_ENG:
        return active_db.smart_suggest_engineer(owner=owner, business_type=business_type, submission_date=submission_date)

    eng_load_pct = 50
    try:
        for e in active_db.get_all_engineers_with_load():
            if e['name'] == suggested_eng:
                eng_load_pct = e['load_pct']
                break
    except Exception:
        pass
    return {
        'name':      suggested_eng,
        'score':     100,
        'reason':    'المهندس الحالي المكلّف بهذه المنافسة',
        'breakdown': f'حمله الحالي: {eng_load_pct}%',
    }


def _with_suggestion(details_json: str, suggestion: dict) -> str:
    try:
        details_dict = json.loads(details_json)
    except Exception:
        details_dict = {}
    details_dict['_smart_suggestion'] = {k: v for k, v in suggestion.items() if k != 'all_scores'}
    return json.dumps(details_dict, ensure_ascii=False, default=str)


MASS_MISSING_RATIO = 0.5        # أكثر من نصف المنافسات النشطة اختفت في دورة واحدة
MASS_MISSING_MIN_ACTIVE = 4     # لا معنى للنسبة مع عدد قليل جداً
MASS_MISSING_HOLD_CYCLES = 24   # ساعتان (دورة كل 5 دقائق) ثم يُعتبر الاختفاء حقيقياً
_mass_missing_streak = 0
# بيانات وضع العرض (DEMO-) ليست من المنصة: لا تُقارن بها — وإلا غيابها عن ملف المصدر = «حذف» وتنبيه أحمر
_MASTER_SQL = f"SELECT * FROM master_tenders WHERE {NOT_DEMO}"


def find_and_stage_changes(db_instance=None, skip_scrape=False) -> int:
    """
    Executes the Scraper -> Loads Excel -> Compares with DB 
    -> Pushes discrepancies to 'pending_changes' table.
    Returns the number of changes staged.
    """
    active_db = db_instance if db_instance else db_default
    
    if not skip_scrape:
        logger.info("Step 1: Running extraction module...")
        try:
            success = portal_adapter.get_active_portal().fetch_to_file()
            if not success:
                logger.warning("Extraction failed. Skipping comparison.")
                return -1
        except Exception as e:
            logger.error(f"Extraction encountered an error: {e}")
            return 0

    logger.info("Step 2: Loading data for comparison...")
    
    # Use Simulation file or Default file
    mock_path = BASE_DIR / "Extracted_Tenders.xlsx"
    target_file = mock_path if mock_path.exists() and skip_scrape else NEW_FILE_DEFAULT
    
    if not target_file.exists():
        logger.error(f"Extracted file not found at {target_file}")
        return 0

    try:
        df_new = pd.read_excel(target_file)
        df_new.columns = df_new.columns.str.strip()
        # ★ DIAGNOSTIC: Show exactly what we downloaded
        logger.info(f"DIAGNOSTIC | Downloaded Excel: {len(df_new)} rows")
        logger.info(f"DIAGNOSTIC | Columns found: {list(df_new.columns)}")
        if 'اسم المنافسة' in df_new.columns:
            logger.info(f"DIAGNOSTIC | First 3 names: {df_new['اسم المنافسة'].head(3).tolist()}")
        else:
            logger.error(f"DIAGNOSTIC | Column 'اسم المنافسة' NOT FOUND! Cannot compare.")
            return 0
    except Exception as e:
        logger.error(f"Failed to read Extracted Excel: {e}")
        return 0

    logger.info("Step 3: Comparing with Master DB...")
    
    # Get master from DB
    with active_db._get_connection() as conn:
        df_master = pd.read_sql(_MASTER_SQL, conn)

    if 'رقم المنافسة' not in df_new.columns:
        df_new['رقم المنافسة'] = ""
    df_new['_identity_key'] = df_new.apply(build_tender_identity, axis=1)
    # مفاتيح سبق ربطها بمنافسات أصلية (بعد تعديل الاسم/المالك في المنصة)
    aliases = _load_aliases(active_db)
    if aliases:
        df_new['_identity_key'] = df_new['_identity_key'].map(lambda k: aliases.get(k, k))
    fallback_count = int(df_new['رقم المنافسة'].apply(lambda v: not is_valid_tender_id(v)).sum())
    if fallback_count:
        logger.warning(
            f"Identity fallback active: {fallback_count}/{len(df_new)} rows have empty 'رقم المنافسة'. "
            "Using stable AUTO-* keys from tender title/owner/type/sector."
        )

    # First Run (Initialization) Concept:
    # If master is totally empty, we assume it's the very first setup on Hostinger.
    # We should auto-approve all of them into master to prevent 1000 Telegram spam messages!
    valid_master_ids = []
    if not df_master.empty and 'tender_id' in df_master.columns:
        valid_master_ids = [
            str(tid).strip()
            for tid in df_master['tender_id'].tolist()
            if is_valid_tender_id(tid) and not str(tid).strip().startswith("LEGACY-")
        ]

    if df_master.empty or not valid_master_ids:
        logger.info("Master DB is extremely empty. Initializing baseline...")
        with active_db._get_connection() as conn:
            conn.execute(
                "DELETE FROM master_tenders WHERE LOWER(TRIM(tender_id)) IN ('nan', 'n/a', 'none', '') OR tender_id LIKE 'LEGACY-%'"
            )
            conn.commit()
        # Map columns to DB schema
        # Assuming Excel has ['رقم المنافسة', 'اسم المنافسة', 'المالك', 'تاريخ التقديم', 'نوع الأعمال', 'القطاع']
        for _, row in df_new.iterrows():
            tender_id = clean_cell(row.get('_identity_key', 'N/A'))
            title = clean_cell(row.get('اسم المنافسة', 'N/A'))
            owner = clean_cell(row.get('المالك', 'N/A'))
            submission_date = clean_cell(row.get('تاريخ التقديم', 'N/A'))
            business_type = clean_cell(row.get('نوع الأعمال', 'N/A'))
            sector = clean_cell(row.get('القطاع', 'N/A'))
            
            with active_db._get_connection() as conn:
                conn.execute('''
                    INSERT OR IGNORE INTO master_tenders 
                    (tender_id, title, owner, submission_date, business_type, sector, assigned_engineer)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (tender_id, title, owner, submission_date, business_type, sector, None))
                conn.commit()
        logger.info("Baseline initialized successfully. Resuming next cycle.")
        return 0

    # Normal Cycle Comparison
    staged_count = 0

    # Normalize names for reliable matching
    # ── PRIMARY IDENTITY ──
    # Switch from Title-based matching to ID-based matching (Fixes Auditor Risk #3)
    master_ids = df_master['tender_id'].astype(str).tolist() if not df_master.empty else []
    # ربط المنافسات المعدّلة في المنصة بأصلها — قبل كشف الإغلاق حتى لا تُغلق الأصلية خطأً
    if _relink_renamed_tenders(active_db, df_new, df_master, set(master_ids)):
        with active_db._get_connection() as conn:
            df_master = pd.read_sql(_MASTER_SQL, conn)
    new_ids = df_new['_identity_key'].astype(str).tolist()

    # ★ DIAGNOSTIC: Show current comparison state
    logger.info(f"DIAGNOSTIC | Portal: {len(new_ids)} tenders | DB Master: {len(master_ids)} tenders")
    # Show tenders in portal but NOT in DB (these should be detected as NEW)
    genuinely_new_ids = [nid for nid in new_ids if nid not in master_ids]
    logger.info(f"DIAGNOSTIC | Tenders in portal NOT in DB (by ID): {len(genuinely_new_ids)}")
    for tid in genuinely_new_ids[:5]:  # Show first 5
        logger.info(f"DIAGNOSTIC |   NEW ID -> {tid}")

    # ── SCENARIO 3: Detect CLOSED tenders (disappeared from portal) ──
    # Split thresholds based on submission deadline:
    #   CLOSE_THRESHOLD_PAST   = 3  → tender deadline already passed: close quickly (15 min)
    #   CLOSE_THRESHOLD_FUTURE = 10 → deadline is still upcoming: wait longer before closing (50 min)
    # This prevents the mismatch between our count and the portal when a tender quietly
    # expires without a formal close event, while still protecting active future tenders
    # from false positives caused by portal export limits or temporary glitches.
    CLOSE_THRESHOLD_PAST   = 3
    CLOSE_THRESHOLD_FUTURE = 10

    active_master_rows = df_master[df_master['status'] != 'CLOSED'].to_dict('records')

    # ── حماية من خلل التصدير: اختفاء جماعي مفاجئ = ملف ناقص من المنصة وليس حذفاً ──
    # (وإلا تُغلق كل المنافسات وتنطلق تنبيهات حذف كاذبة). الحجز مؤقت: إن استمر الاختفاء
    # MASS_MISSING_HOLD_CYCLES دورة متتالية يُعتبر حقيقياً ويكمل المسار العادي.
    global _mass_missing_streak
    missing_now = [m for m in active_master_rows if str(m['tender_id']) not in set(new_ids)]
    mass_missing = len(active_master_rows) >= MASS_MISSING_MIN_ACTIVE and         len(missing_now) / len(active_master_rows) > MASS_MISSING_RATIO
    if mass_missing and _mass_missing_streak < MASS_MISSING_HOLD_CYCLES:
        _mass_missing_streak += 1
        logger.warning(
            f"MASS DISAPPEARANCE: {len(missing_now)}/{len(active_master_rows)} active tenders missing from export "
            f"— treating as portal glitch, closure paused ({_mass_missing_streak}/{MASS_MISSING_HOLD_CYCLES})"
        )
        active_master_rows = []
    elif not mass_missing:
        _mass_missing_streak = 0

    for m_row in active_master_rows:
        m_id = str(m_row['tender_id'])
        current_title    = str(m_row['title'])
        submission_date  = str(m_row.get('submission_date', '') or '')
        if m_id not in new_ids:
            with active_db._get_connection() as conn:
                # Increment missing counter
                conn.execute("UPDATE master_tenders SET missing_seen_count = missing_seen_count + 1 WHERE tender_id = ?", (m_id,))

                # Check if it reached the threshold for closure
                res = conn.execute("SELECT missing_seen_count FROM master_tenders WHERE tender_id = ?", (m_id,)).fetchone()
                missing_count = res[0] if res else 0

                # Choose threshold based on whether the deadline is still in the future
                submission_dt = pd.to_datetime(submission_date, errors='coerce')
                deadline_is_future = (
                    pd.notnull(submission_dt) and
                    submission_dt.replace(tzinfo=None) > pd.Timestamp.now()
                )
                threshold = CLOSE_THRESHOLD_FUTURE if deadline_is_future else CLOSE_THRESHOLD_PAST

                if missing_count >= threshold:
                    if deadline_is_future:
                        # Extra safety log for future-deadline auto-close (unusual case)
                        logger.warning(
                            f"AUTO-CLOSE (future deadline) for '{current_title}': "
                            f"submission date {submission_date} but missing {missing_count} consecutive cycles."
                        )

                    conn.execute("UPDATE master_tenders SET status = 'CLOSED', updated_at = CURRENT_TIMESTAMP WHERE tender_id = ?", (m_id,))
                    logger.info(f"SAFE CLOSED: Tender missing for {threshold} cycles -> {m_id}")
                    # اختفت قبل موعدها = حُذفت/أُلغيت من المنصة → تنبيه عاجل (DELETED)،
                    # اختفت بعد موعدها = انتهت طبيعياً → إشعار هادئ (CLOSED) كما كان.
                    # (2026-09-19: منافستان اختفتا قبل موعدهما بأسبوع وجاءهما سطر "للعلم" فقط.)
                    change_type = "DELETED" if deadline_is_future else "CLOSED"
                    details = {"owner": m_row.get("owner"), "engineer": m_row.get("assigned_engineer"),
                               "submission_date": submission_date[:10],
                               "missing_cycles": int(missing_count)} if deadline_is_future else {}
                    active_db.add_pending_change(
                        tender_id=m_id,
                        title=current_title,
                        change_type=change_type,
                        submission_date=submission_date[:10] if deadline_is_future else "N/A",
                        details_json=json.dumps(details, ensure_ascii=False, default=str),
                        suggested_eng=m_row.get("assigned_engineer") if deadline_is_future else "مدير النظام",
                        conn=conn
                    )
                    active_db.log_audit("AUTO_DELETE" if deadline_is_future else "AUTO_CLOSE", m_id,
                                        f"{'Removed before deadline' if deadline_is_future else 'Disappeared'}: {current_title}",
                                        "SystemScraper", conn=conn)
                else:
                    logger.info(f"MISSING (Quarantine): {m_id} (Seen missing {missing_count}/{threshold} times)")
                conn.commit()

    for index, row in df_new.iterrows():
        tender_id = clean_cell(row.get('_identity_key', 'N/A'))
        name = clean_cell(row.get('اسم المنافسة', 'N/A'))
        new_date = clean_cell(row.get('تاريخ التقديم', 'N/A'))

        # GUARD: Reject rows with missing/invalid tender_id to prevent 'nan' duplicates
        if not is_valid_tender_id(tender_id):
            logger.warning(f"Skipping row with invalid tender_id='{tender_id}' | tender: {name[:50]}")
            continue
        
        # Build JSON full row to preserve all columns in the DB pending payload
        details_json = row.to_json(force_ascii=False)
        
        # Anti-Spam Check: Is it already in the pending queue (PENDING or NOTIFIED)?
        with active_db._get_connection() as conn:
            all_pending_ids = [r[0] for r in conn.execute("SELECT tender_id FROM pending_changes WHERE status IN ('PENDING_APPROVAL', 'NOTIFIED')").fetchall()]
        already_pending = tender_id in all_pending_ids

        if already_pending:
            logger.debug(f"Skipping already-pending tender_id='{tender_id}'")
            continue

        if tender_id not in master_ids:
            # IT'S A NEW TENDER
            logger.info(f"Detected NEW Tender: {tender_id} - {name}")
            owner         = clean_cell(row.get('المالك', 'N/A'))
            business_type = clean_cell(row.get('نوع الأعمال', 'N/A'))
            suggestion    = active_db.smart_suggest_engineer(owner=owner, business_type=business_type, submission_date=new_date)
            suggested_eng = suggestion['name']
            # Embed suggestion into details so the Telegram card can display it
            import json as _json
            try:
                details_dict = _json.loads(details_json)
            except Exception:
                details_dict = {}
            details_dict['_smart_suggestion'] = {k: v for k, v in suggestion.items() if k != 'all_scores'}
            details_json = _json.dumps(details_dict, ensure_ascii=False, default=str)
            active_db.add_pending_change(
                tender_id=tender_id,
                title=name,
                change_type="NEW",
                submission_date=new_date,
                details_json=details_json,
                suggested_eng=suggested_eng
            )
            active_db.log_audit("DETECT_NEW", tender_id, f"New tender found: {name}", "SystemScraper")
            staged_count += 1
            
        else:
            # TENDER EXISTS -> Reset missing counter (it's back or still there)
            with active_db._get_connection() as conn:
                conn.execute("UPDATE master_tenders SET missing_seen_count = 0 WHERE tender_id = ?", (tender_id,))
                conn.commit()

            # Check for Date Modification (using ID matching)
            master_row = df_master[df_master['tender_id'].astype(str) == tender_id]

            # ── Tender came back after being CLOSED (e.g. portal glitch longer than
            # the close threshold). Without this it stayed CLOSED silently.
            # Approving REOPENED sets status back to InProgress (db.approve_change).
            if not master_row.empty and str(master_row.iloc[0].get('status')) == 'CLOSED':
                with active_db._get_connection() as _rconn:
                    _rconn.execute(
                        "UPDATE master_tenders SET portal_last_seen_date=? WHERE tender_id=?",
                        (new_date, tender_id)
                    )
                    # Admin already rejected reopening this tender → respect it, don't re-ask every cycle
                    declined = _rconn.execute(
                        "SELECT 1 FROM pending_changes WHERE tender_id=? AND change_type='REOPENED' "
                        "AND status IN ('REJECTED', 'CLEANED') LIMIT 1", (tender_id,)
                    ).fetchone()
                    _rconn.commit()
                if declined:
                    logger.debug(f"REOPEN declined earlier by admin — keeping {tender_id} CLOSED")
                    continue
                owner         = clean_cell(row.get('المالك', 'N/A'))
                business_type = clean_cell(row.get('نوع الأعمال', 'N/A'))
                suggestion    = _engineer_suggestion(active_db, master_row.iloc[0].to_dict(), owner, business_type, new_date)
                logger.info(f"Detected REOPENED tender (back on portal after CLOSED): {tender_id} - {name}")
                active_db.add_pending_change(
                    tender_id=tender_id,
                    title=name,
                    change_type="REOPENED",
                    submission_date=new_date,
                    details_json=_with_suggestion(details_json, suggestion),
                    suggested_eng=suggestion['name']
                )
                active_db.log_audit("DETECT_REOPEN", tender_id, f"Closed tender back on portal: {name}", "SystemScraper")
                staged_count += 1
                continue

            if not master_row.empty:
                # ── Use portal_last_seen_date for comparison, NOT submission_date ──
                # submission_date may have been manually overridden by the user via
                # the dashboard, so comparing against it would keep triggering false
                # "portal changed the date" notifications every engine cycle.
                # portal_last_seen_date tracks what the portal actually showed last
                # time — we only notify when the portal itself changes, not when it
                # disagrees with a manual override.
                # NaN is truthy in Python, so `nan or fallback` returns nan —
                # clean_cell() treats NaN/None/'nan' as empty and fixes that trap.
                old_portal_str = (clean_cell(master_row.iloc[0].get('portal_last_seen_date'), default="")
                                  or clean_cell(master_row.iloc[0].get('submission_date'), default=""))

                # Always update portal_last_seen_date to the current scraped value
                # so next cycle has an accurate baseline even if no change is detected.
                with active_db._get_connection() as _pconn:
                    _pconn.execute(
                        "UPDATE master_tenders SET portal_last_seen_date=? WHERE tender_id=?",
                        (new_date, tender_id)
                    )
                    _pconn.commit()

                # Robust date comparison using pandas to normalize the strings
                old_date_parsed = pd.to_datetime(old_portal_str, errors='coerce')
                new_date_parsed = pd.to_datetime(new_date, errors='coerce')

                is_changed = False
                if pd.notnull(old_date_parsed) and pd.notnull(new_date_parsed):
                    is_changed = (old_date_parsed != new_date_parsed)
                else:
                    is_changed = (new_date != old_portal_str)

                date_is_locked = bool(master_row.iloc[0].get('date_locked', 0))
                if date_is_locked and is_changed:
                    logger.info(f"DATE LOCKED: ignoring portal date change for {tender_id} ({old_portal_str} -> {new_date})")
                elif is_changed:
                    logger.info(f"Detected PORTAL DATE CHANGE for {tender_id}: ({old_portal_str} -> {new_date})")
                    owner         = clean_cell(row.get('المالك', 'N/A'))
                    business_type = clean_cell(row.get('نوع الأعمال', 'N/A'))
                    # For a date change the responsible engineer stays the same (AI only if unassigned)
                    suggestion    = _engineer_suggestion(active_db, master_row.iloc[0].to_dict(), owner, business_type, new_date)
                    suggested_eng = suggestion['name']
                    details_json  = _with_suggestion(details_json, suggestion)
                    active_db.add_pending_change(
                        tender_id=tender_id,
                        title=name,
                        change_type="UPDATED_DATE",
                        submission_date=new_date,
                        details_json=details_json,
                        suggested_eng=suggested_eng
                    )
                    active_db.log_audit("DETECT_CHANGE", tender_id, f"Portal date change: {old_portal_str} -> {new_date}", "SystemScraper")
                    staged_count += 1

    logger.info(f"Comparison complete. {staged_count} changes staged for Human Approval.")
    return staged_count

if __name__ == "__main__":
    finding_count = find_and_stage_changes()
    print(f"Staged {finding_count} new pending items.")
