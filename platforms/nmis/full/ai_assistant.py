# -*- coding: utf-8 -*-
"""AI assistant core: OpenAI client, persistent chat memory, knowledge base,
live-DB context and the main _ai_reply pipeline. Extracted verbatim from
bot_daemon.py on 2026-07-05. Telegram-free - unit-testable in isolation.
bot_daemon must call configure(db, track_error) after import."""
import os, time, threading, logging
from pathlib import Path

logger = logging.getLogger("BotDaemon")   # same name -> identical log stream
BASE_DIR = Path(__file__).parent

try:
    from openai import OpenAI as _OpenAIClient
    _OPENAI_IMPORT_OK = True
except Exception:
    _OpenAIClient = None
    _OPENAI_IMPORT_OK = False

# injected from bot_daemon via configure()
db = None
def _track_error(error_key, detail=""):   # no-op until configure()
    pass

def configure(db_instance, track_error=None):
    """Wire runtime dependencies owned by bot_daemon."""
    global db, _track_error
    db = db_instance
    if track_error is not None:
        _track_error = track_error


# النموذج قابل للتغيير من .env بدون تعديل الكود (للرجوع: AI_MODEL=gpt-4o)
# gpt-6-luna (2026-09-23): أرخص من gpt-4o بـ 20-25 ضعفاً ($0.10/$0.50 لكل مليون token)
# وأفضل جودة عربية في مقارنة فعلية. نموذج "تفكير": لا يقبل temperature مع التفكير،
# وتوكنات التفكير تُحسب من max_completion_tokens — لذلك الصوت والتلخيص بدون تفكير.
AI_MODEL        = os.getenv("AI_MODEL", "gpt-6-luna").strip()
AI_REASONING_EFFORT = os.getenv("AI_REASONING_EFFORT", "low").strip()   # none|low|medium|high
_REASONING_MODEL = not AI_MODEL.startswith(("gpt-4", "gpt-3"))


def _effort_kw(effort: str) -> dict:
    """reasoning_effort للنماذج التي تدعمه فقط (gpt-4o لا يقبله)."""
    return {"reasoning_effort": effort} if _REASONING_MODEL and effort else {}

AI_MAX_HISTORY  = 14   # messages to remember per user session

_OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")

if _OPENAI_IMPORT_OK and _OPENAI_KEY:
    _ai_client = _OpenAIClient(api_key=_OPENAI_KEY)
    AI_ENABLED = True
else:
    _ai_client = None
    AI_ENABLED = False

_ai_history: dict = {}          # chat_id → list[{role, content}]

_AI_LOCK = threading.Lock()     # prevent parallel AI calls from same user

_AI_HISTORY_DB = BASE_DIR / "ai_history.db"

def _history_db_init():
    import sqlite3
    con = sqlite3.connect(_AI_HISTORY_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS ai_history (
        chat_id   INTEGER NOT NULL,
        role      TEXT    NOT NULL,
        content   TEXT    NOT NULL,
        ts        INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ah_chat ON ai_history(chat_id, ts)")
    con.commit(); con.close()

def _history_load(chat_id: int) -> list:
    import sqlite3
    try:
        con = sqlite3.connect(_AI_HISTORY_DB)
        rows = con.execute(
            "SELECT role, content FROM ai_history WHERE chat_id=? ORDER BY ts DESC LIMIT ?",
            (chat_id, AI_MAX_HISTORY)
        ).fetchall()
        con.close()
        return [{"role": r, "content": c} for r, c in reversed(rows)]
    except Exception:
        return []

_COMPRESS_THRESHOLD = AI_MAX_HISTORY * 3   # اضغط عند تجاوز هذا العدد

def _history_compress(chat_id: int, messages: list) -> list:
    """
    بدلاً من حذف الرسائل القديمة، لخّصها في رسالة واحدة.
    يحافظ على السياق البعيد دون استهلاك tokens زائدة.
    """
    if not AI_ENABLED or len(messages) <= AI_MAX_HISTORY:
        return messages
    old  = messages[:-AI_MAX_HISTORY]
    keep = messages[-AI_MAX_HISTORY:]
    # بناء نص للتلخيص
    conv = "\n".join(f"{m['role']}: {m['content']}" for m in old)
    try:
        resp = _ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[{
                "role": "system",
                "content": "لخّص هذه المحادثة في جملتين بالعربية. ركّز على المعلومات المهمة فقط."
            }, {"role": "user", "content": conv}],
            max_completion_tokens=150,
            **_effort_kw("none"),
        )
        summary = resp.choices[0].message.content.strip()
        summary_msg = {"role": "system",
                       "content": f"[ملخص محادثة سابقة: {summary}]"}
        compressed = [summary_msg] + keep
        logger.info(f"History compressed for chat_id={chat_id}: {len(old)} → 1 summary")
        return compressed
    except Exception as e:
        logger.debug(f"History compression failed: {e}")
        return keep   # fallback: احتفظ بالأحدث فقط

def _history_save(chat_id: int, role: str, content: str):
    import sqlite3
    try:
        con = sqlite3.connect(_AI_HISTORY_DB)
        con.execute("INSERT INTO ai_history(chat_id,role,content) VALUES(?,?,?)",
                    (chat_id, role, content))
        # keep only last AI_MAX_HISTORY*2 rows per user
        con.execute("""DELETE FROM ai_history WHERE chat_id=? AND ts NOT IN (
            SELECT ts FROM ai_history WHERE chat_id=? ORDER BY ts DESC LIMIT ?)""",
            (chat_id, chat_id, AI_MAX_HISTORY * 2))
        con.commit(); con.close()
    except Exception as e:
        logger.debug(f"history_save error: {e}")

def _history_clear(chat_id: int):
    import sqlite3
    try:
        con = sqlite3.connect(_AI_HISTORY_DB)
        con.execute("DELETE FROM ai_history WHERE chat_id=?", (chat_id,))
        con.commit(); con.close()
    except Exception:
        pass

_history_db_init()

_DIALECT_PROMPTS = {
    "فصحى":  "",   # لا إضافة — الـ system prompt الأصلي يكفي
    "مصري":  "\n\nمهم جداً: ردودك دايماً بالعامية المصرية البسيطة. استخدم كلمات زي: إزيك، تمام، عندنا، إيه، مش، دلوقتي، كمان، بس، يعني، طب. خلي ردودك طبيعية وودودة زي ما بيتكلم المصريين.",
    "خليجي": "\n\nمهم جداً: ردودك دايماً باللهجة الخليجية. استخدم كلمات مثل: شلونك، زين، وش، الحين، بعدين، ما قدرت، صح، لا والله، إي.",
}

_dialect_per_user: dict = {}   # chat_id → dialect name (default: AI_DEFAULT_DIALECT)
# اللهجة الافتراضية للردود (2026-09-23 اختيار المالك: مصري) — /dialect لكل محادثة، أو AI_DEFAULT_DIALECT في .env
AI_DEFAULT_DIALECT = os.getenv("AI_DEFAULT_DIALECT", "مصري").strip()

from company_profile import PROFILE as _CO_PROFILE
_CO_SHORT = (_CO_PROFILE.get("short_ar") or "").strip() or "الشركة"
_CO_SYSTEM = (_CO_PROFILE.get("system_title") or "").strip() or "نظام متابعة المنافسات"
_CO_TEAM = (_CO_PROFILE.get("team_ar") or "").strip() or "فريق العروض الفنية"
_CO_DEPT = (_CO_PROFILE.get("department_ar") or "").strip() or "قسم العروض الفنية"
_CO_SCOPE = (_CO_PROFILE.get("ai_scope_ar") or "").strip() or "المناقصات ومتابعة العروض الفنية"

_AI_SYSTEM = (
    f"أنت مساعد ذكي متخصص حصراً في {_CO_SYSTEM} لمتابعة المناقصات،\n"
    f"تم برمجتك من قِبَل فريق العمل ب{_CO_DEPT} بشركة {_CO_SHORT}.\n"
    "النظام يراقب مصدر بيانات المنافسات تلقائياً، يكتشف المناقصات الجديدة وتعديلات المواعيد،\n"
    f"ويُنبّه {_CO_TEAM} فور حدوث أي تغيير.\n\n"
    "نطاق تخصصك (ما يُسمح لك بالإجابة عنه):\n"
    f"- {_CO_SCOPE}\n"
    "- بيانات النظام: المناقصات النشطة، المواعيد، المهندسون، الأحمال\n"
    "- إجراءات العروض الفنية والمالية\n"
    f"- الأسئلة المتعلقة بعمل {_CO_TEAM} بشركة {_CO_SHORT}\n"
    f"- معلومات عن شركة {_CO_SHORT}: نبذتها، مهندسيها، تخصصاتها، مشاريعها\n"
    "- أي سؤال وارد في قاعدة المعرفة المرفقة\n\n"
    "قواعد صارمة:\n"
    "- تحدّث دائماً بالعربية الفصحى المبسطة\n"
    "- كن مختصراً وعملياً\n"
    "- إذا سُئلت عن أرقام حية (مناقصات، مهندسين، إلخ) استخدم البيانات المرفقة\n"
    "- لا تختلق معلومات — إذا لم تعرف قل ذلك بوضوح\n"
    f"- إذا سألك المستخدم عن أي موضوع خارج نطاق شركة {_CO_SHORT} والمناقصات\n"
    "  (مثل: أخبار عامة، رياضة، طبخ، سياسة، ترفيه، أي شركة أخرى، إلخ)\n"
    "  فيجب أن تردّ بهذه العبارة حرفياً دون أي إضافة:\n"
    "  «أنا غير مصرح لي إلا بما تم برمجتي عليه فقط من فريق العمل بقسم العروض الفنية.\n"
    "   أنا هنا لمساعدتك بتخصصي، اسأل ما شئت إن كان بمجال تخصصي.\n"
    "   غير ذلك فلا أستطيع.»\n"
)

def _ai_load_knowledge() -> str:
    """Load all .md knowledge files from the knowledge/ folder on the server."""
    from instance_paths import KNOWLEDGE_DIR
    knowledge_dir = KNOWLEDGE_DIR   # KNOWLEDGE_DIR في .env لكل نسخة
    if not knowledge_dir.exists():
        return ""
    parts = []
    for md_file in sorted(knowledge_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                parts.append(f"=== {md_file.stem} ===\n{content}")
        except Exception:
            pass
    if parts:
        combined = "\n\n".join(parts)
        logger.info(f"AI knowledge base loaded: {len(parts)} files, {len(combined)} chars")
        return combined
    return ""

_AI_KNOWLEDGE = _ai_load_knowledge()

AI_CONTEXT_MAX_TENDERS = 80   # سقف أمان لحجم السياق (اليوم ~22 منافسة نشطة ≈ 2k token ≈ $0.0002)
_AR_WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def _ai_live_context() -> str:
    """
    بيانات حية تُحقن في كل طلب للمساعد الذكي.
    (2026-09-23) كل المنافسات النشطة بأسمائها الكاملة — كان يُرسَل فقط ما ينتهي خلال 7 أيام
    ومقصوصاً عند 55 حرفاً، فكان يرد "مش متاح عندي" ويذكر أسماء مبتورة.
    """
    try:
        with db._get_connection() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) FROM pending_changes WHERE status IN ('PENDING_APPROVAL','NOTIFIED')"
            ).fetchone()[0]
            tenders = conn.execute("""
                SELECT title, COALESCE(owner,'—') AS owner, submission_date,
                       COALESCE(assigned_engineer,'—') AS eng,
                       CAST(julianday(date(submission_date)) - julianday(date('now','localtime')) AS INTEGER) AS days_left
                FROM master_tenders
                WHERE status NOT IN ('CLOSED','REJECTED')
                ORDER BY date(submission_date) IS NULL, date(submission_date)
            """).fetchall()
            engs = conn.execute("""
                SELECT e.name, COUNT(t.id) as cnt
                FROM engineers e
                LEFT JOIN master_tenders t
                  ON t.assigned_engineer = e.name
                 AND t.status NOT IN ('CLOSED','REJECTED')
                GROUP BY e.name ORDER BY cnt DESC
            """).fetchall()
        today = time.localtime()
        lines = [
            f"[بيانات النظام المباشرة — {time.strftime('%Y-%m-%d %H:%M', today)}، اليوم {_AR_WEEKDAYS[today.tm_wday]}]",
            f"المنافسات النشطة: {len(tenders)}",
            f"طلبات بانتظار الاعتماد: {pending}",
        ]
        if tenders:
            lines.append("كل المنافسات النشطة (الاسم | الجهة | موعد التقديم | الأيام المتبقية | المهندس):")
            for r in tenders[:AI_CONTEXT_MAX_TENDERS]:
                dl = r["days_left"]
                left = "—" if dl is None else ("انتهى" if dl < 0 else ("اليوم" if dl == 0 else f"{dl} يوم"))
                lines.append(f"  • {r['title']} | {r['owner']} | {str(r['submission_date'] or '—')[:10]} | {left} | {r['eng']}")
            if len(tenders) > AI_CONTEXT_MAX_TENDERS:
                lines.append(f"  … و{len(tenders) - AI_CONTEXT_MAX_TENDERS} منافسة أخرى (اطلب من المستخدم استخدام /list_d للقائمة الكاملة)")
        if engs:
            lines.append("أحمال المهندسين:")
            for e in engs:
                lines.append(f"  • {e['name']}: {e['cnt']} منافسة")
        return "\n".join(lines)
    except Exception as ex:
        logger.debug(f"AI context error: {ex}")
        return ""

_VOICE_MODE_SUFFIX = (
    "\n\nتعليمات إضافية للرد الصوتي: "
    "ردك سيُحوَّل إلى صوت مباشرة. "
    "اجعل ردك قصيراً جداً (٣-٤ جمل كحد أقصى). "
    "لا تستخدم قوائم أو نقاط أو أرقام متسلسلة. "
    "تحدث بأسلوب طبيعي كما لو كنت تتحدث على الهاتف. "
    "مهم جداً: لا تكتب أي كلمة بالإنجليزية إطلاقاً — عرّب كل شيء. "
    "مثال: بدلاً من AI قل 'الذكاء الاصطناعي'، بدلاً من API قل 'واجهة البرمجة'."
)

_VOICE_MODE_SUFFIX_MASRI = (
    "\n\nتعليمات الرد الصوتي: "
    "ردك هيتحوّل لصوت على طول. "
    "خلي ردك قصير جداً (٣-٤ جمل بحد أقصى). "
    "اتكلم بالعامية المصرية البسيطة — زي ما بتتكلم على التليفون. "
    "استخدم كلمات زي: تمام، دلوقتي، بعدين، لقيت، مش، يعني، بس، كمان. "
    "ما تستخدمش قوايم أو نقاط أو ترقيم. "
    "مهم: ما تكتبش أي كلمة بالإنجليزي خالص — عرّب كل حاجة."
)

_ARABIC_ONLY_SUFFIX = (
    "\n\nمهم: اكتب ردودك بالعربية الخالصة دائماً. "
    "لا تستخدم أي كلمة إنجليزية. عرّب كل مصطلح تقني."
)

def _ai_reply(chat_id: int, user_text: str, voice_mode: bool = False) -> str:
    """Core function: send user_text → GPT → return Arabic reply."""
    if not AI_ENABLED:
        return "⚠️ خاصية المساعد الذكي غير مفعّلة. تأكد من إضافة OPENAI_API_KEY في الإعدادات."
    with _AI_LOCK:
        # Load history: RAM first, fallback to DB
        if chat_id not in _ai_history:
            _ai_history[chat_id] = _history_load(chat_id)
        hist = _ai_history[chat_id]
        hist.append({"role": "user", "content": user_text})
        _history_save(chat_id, "user", user_text)
        # ضغط الذاكرة إذا تجاوزت الحد — بدلاً من الحذف المباشر
        if len(hist) >= _COMPRESS_THRESHOLD:
            _ai_history[chat_id] = _history_compress(chat_id, hist)
            hist = _ai_history[chat_id]
        elif len(hist) > AI_MAX_HISTORY:
            hist[:] = hist[-AI_MAX_HISTORY:]
        ctx = _ai_live_context()
        # Build full system message
        dialect = _dialect_per_user.get(chat_id, AI_DEFAULT_DIALECT)
        sys_msg = _AI_SYSTEM + _DIALECT_PROMPTS.get(dialect, "") + _ARABIC_ONLY_SUFFIX
        if voice_mode:
            # استخدم prompt مصري لو المستخدم اختار اللهجة المصرية
            sys_msg += _VOICE_MODE_SUFFIX_MASRI if dialect == "مصري" else _VOICE_MODE_SUFFIX
        if _AI_KNOWLEDGE:
            sys_msg += "\n\n## قاعدة المعرفة الخاصة بالشركة:\n" + _AI_KNOWLEDGE
        if ctx:
            sys_msg += "\n\n## البيانات الحية الآن:\n" + ctx
        try:
            resp = _ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "system", "content": sys_msg}] + hist,
                max_completion_tokens=300 if voice_mode else 1200,
                # الصوت: بلا تفكير (سرعة + لا يستهلك التفكير ميزانية الـ 300 token)
                **_effort_kw("none" if voice_mode else AI_REASONING_EFFORT),
            )
            reply = resp.choices[0].message.content.strip()
            hist.append({"role": "assistant", "content": reply})
            _history_save(chat_id, "assistant", reply)
            logger.info(f"AI chat: user={chat_id} voice={voice_mode} q={user_text[:60]!r} → {len(reply)} chars")
            return reply
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            err = str(e)
            _track_error("OpenAI GPT", err[:120])   # ← تنبيه تلقائي
            if "model" in err.lower():
                return f"⚠️ النموذج '{AI_MODEL}' غير متاح حالياً. تواصل مع المسؤول."
            if "quota" in err.lower() or "billing" in err.lower():
                return "⚠️ رصيد OpenAI API نفد أو الحساب غير مفعّل."
            return f"⚠️ خطأ في المساعد الذكي: {err[:120]}"

