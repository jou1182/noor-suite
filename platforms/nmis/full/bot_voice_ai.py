# -*- coding: utf-8 -*-
"""AI chat assistant + voice (Whisper/TTS) handlers.

Split out of bot_daemon.py on 2026-09-23 (behaviour unchanged)."""
import os
import time
import voice_lists
from bot_core import WHISPER_DOMAIN_PROMPT, WHISPER_MODEL, _track_error, bot, db, is_authorized, logger
# ============================================================
# 5b. AI CHAT ASSISTANT  (OpenAI GPT + Whisper voice)
# ============================================================

# ── Initialise client ────────────────────────────────────────
import ai_assistant
from ai_assistant import (AI_DEFAULT_DIALECT, AI_MODEL, AI_MAX_HISTORY, AI_ENABLED, _ai_client,
                          _ai_history, _AI_LOCK, _history_load, _history_save,
                          _history_clear, _history_compress, _dialect_per_user,
                          _DIALECT_PROMPTS, _AI_SYSTEM, _AI_KNOWLEDGE,
                          _ai_load_knowledge, _ai_live_context, _ai_reply,
                          _VOICE_MODE_SUFFIX, _VOICE_MODE_SUFFIX_MASRI,
                          _ARABIC_ONLY_SUFFIX)
ai_assistant.configure(db, _track_error)
# _OPENAI_KEY: moved to ai_assistant.py
# CLIENT_INIT: moved to ai_assistant.py

# _ai_history: moved to ai_assistant.py
# _AI_LOCK: moved to ai_assistant.py

# ── Persistent AI history (SQLite) ────────────────────────────
# _AI_HISTORY_DB: moved to ai_assistant.py

# _history_db_init: moved to ai_assistant.py

# _history_load: moved to ai_assistant.py

# _COMPRESS_THRESHOLD: moved to ai_assistant.py

# _history_compress: moved to ai_assistant.py


# _history_save: moved to ai_assistant.py

# _history_clear: moved to ai_assistant.py

# DB_INIT_CALL: moved to ai_assistant.py

# ── Per-user runtime state ─────────────────────────────────────
_last_voice_reply:  dict = {}   # chat_id → last audio bytes (for /repeat)
_voicemode_users:   set  = set()# chat_id → always reply with voice
_voice_rate_limit:  dict = {}   # chat_id → last voice message timestamp

# TTS voices — user can switch with /voice command
_TTS_VOICES = {
    "1": ("onyx",    "رجل — صوت عميق"),
    "2": ("echo",    "رجل — صوت متوسط"),
    "3": ("fable",   "رجل — صوت ناعم"),
    "4": ("nova",    "امرأة — صوت طبيعي"),
    "5": ("shimmer", "امرأة — صوت ناعم"),
}
_tts_voice_per_user: dict = {}   # chat_id → voice name (default: DEFAULT_TTS_VOICE)
# الصوت الافتراضي (2026-09-23 اختيار المالك: Kore من Google = "nova") — قابل للتغيير من .env
DEFAULT_TTS_VOICE = os.getenv("TTS_DEFAULT_VOICE", "nova").strip()

# Dialect settings per user
_DIALECTS = {
    "1": ("فصحى",   "اللغة العربية الفصحى"),
    "2": ("مصري",   "العامية المصرية 🇪🇬 — الافتراضي"),
    "3": ("خليجي",  "اللهجة الخليجية 🇸🇦"),
}
# _DIALECT_PROMPTS: moved to ai_assistant.py
# _dialect_per_user: moved to ai_assistant.py

# _AI_SYSTEM: moved to ai_assistant.py

# _ai_load_knowledge: moved to ai_assistant.py

# Load knowledge base once at startup (reloaded on bot restart after upload)
# _AI_KNOWLEDGE: moved to ai_assistant.py


# _ai_live_context: moved to ai_assistant.py

# _VOICE_MODE_SUFFIX: moved to ai_assistant.py

# نسخة مصرية من الـ prompt الصوتي — تُستخدَم لما المستخدم يختار اللهجة المصرية
# _VOICE_MODE_SUFFIX_MASRI: moved to ai_assistant.py

# نفس التعليمات للردود النصية — عربي خالص دائماً
# _ARABIC_ONLY_SUFFIX: moved to ai_assistant.py

# _ai_reply: moved to ai_assistant.py


@bot.message_handler(commands=['reset'])
def handle_ai_reset(message):
    """Clear conversation history for this user (RAM + DB)."""
    if not is_authorized(message): return
    _ai_history.pop(message.chat.id, None)
    _history_clear(message.chat.id)
    bot.send_message(message.chat.id, "🔄 تم مسح سجل المحادثة. ابدأ محادثة جديدة!")


@bot.message_handler(commands=['repeat'])
def handle_repeat(message):
    """Resend last voice reply."""
    if not is_authorized(message): return
    audio = _last_voice_reply.get(message.chat.id)
    if not audio:
        bot.send_message(message.chat.id, "⚠️ لا يوجد رد صوتي سابق لإعادته.")
        return
    import io
    buf = io.BytesIO(audio); buf.name = "reply.ogg"
    bot.send_voice(message.chat.id, buf)


@bot.message_handler(commands=['voicemode'])
def handle_voicemode(message):
    """Toggle: all replies as voice, regardless of input type."""
    if not is_authorized(message): return
    cid = message.chat.id
    if cid in _voicemode_users:
        _voicemode_users.discard(cid)
        bot.send_message(cid, "🔇 وضع الصوت الدائم: *مُوقَف*\nالردود النصية ستعود نصاً.",
                         parse_mode="Markdown")
    else:
        _voicemode_users.add(cid)
        bot.send_message(cid, "🔊 وضع الصوت الدائم: *مُفعَّل*\nجميع ردودي ستكون صوتاً الآن.",
                         parse_mode="Markdown")


@bot.message_handler(commands=['voice'])
def handle_voice_select(message):
    """Let user pick TTS voice."""
    if not is_authorized(message): return
    parts = message.text.strip().split()
    if len(parts) == 1:
        # Show menu
        current_voice = _tts_voice_per_user.get(message.chat.id, DEFAULT_TTS_VOICE)
        lines = ["🎙️ *اختر صوت الردود الصوتية:*\n"]
        for num, (vname, vdesc) in _TTS_VOICES.items():
            marker = "✅" if vname == current_voice else "  "
            lines.append(f"{marker} /voice {num}  —  {vdesc}")
        lines.append(f"\n_الصوت الحالي: {current_voice}_")
        bot.send_message(message.chat.id, "\n".join(lines), parse_mode="Markdown")
    elif parts[1] in _TTS_VOICES:
        voice_name, voice_desc = _TTS_VOICES[parts[1]]
        _tts_voice_per_user[message.chat.id] = voice_name
        bot.send_message(message.chat.id,
                         f"✅ تم تغيير الصوت إلى: *{voice_desc}*\n"
                         f"سيُطبّق على ردودك الصوتية القادمة.",
                         parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ رقم غير صحيح. اكتب /voice لرؤية الخيارات.")


@bot.message_handler(commands=['dialect'])
def handle_dialect_select(message):
    """Let user pick reply dialect (فصحى / مصري / خليجي)."""
    if not is_authorized(message): return
    parts = message.text.strip().split()
    if len(parts) == 1:
        current = _dialect_per_user.get(message.chat.id, AI_DEFAULT_DIALECT)
        lines = ["🗣️ *اختر لهجة الردود:*\n"]
        for num, (dname, ddesc) in _DIALECTS.items():
            marker = "✅" if dname == current else "  "
            lines.append(f"{marker} /dialect {num}  —  {ddesc}")
        lines.append(f"\n_اللهجة الحالية: {current}_")
        bot.send_message(message.chat.id, "\n".join(lines), parse_mode="Markdown")
    elif parts[1] in _DIALECTS:
        dialect_name, dialect_desc = _DIALECTS[parts[1]]
        _dialect_per_user[message.chat.id] = dialect_name
        bot.send_message(message.chat.id,
                         f"✅ تم تغيير اللهجة إلى: *{dialect_desc}*\n"
                         f"سيُطبّق على جميع ردودي القادمة.",
                         parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "⚠️ رقم غير صحيح. اكتب /dialect لرؤية الخيارات.")


# ── قاموس النطق المخصص (شامل) ────────────────────────────────
from tts_text import (_PRONUNCIATION_DICT, _ARABIC_PHONETIC_CORRECTIONS,
                      _EN_PHONETIC, _transliterate, _apply_pronunciation,
                      _num_to_ar, _tts_prepare, _split_for_tts)
# _PRONUNCIATION_DICT: moved to tts_text.py

# ── تصحيح نطق الكلمات العربية بالعامية المصرية ──────────────
# _ARABIC_PHONETIC_CORRECTIONS: moved to tts_text.py

# نقل صوتي للحروف الإنجليزية → عربية (للكلمات غير الموجودة بالقاموس)
# _EN_PHONETIC: moved to tts_text.py

# _transliterate: moved to tts_text.py

# _apply_pronunciation: moved to tts_text.py


# _num_to_ar: moved to tts_text.py


# _tts_prepare: moved to tts_text.py


# ── تعيين صوت Google TTS بناءً على اختيار المستخدم ─────────────
_GOOGLE_VOICE_MAP = {
    "onyx":    "ar-XA-Chirp3-HD-Charon",   # ذكر  — مختار من المستخدم ⭐
    "echo":    "ar-XA-Chirp3-HD-Charon",   # ذكر
    "fable":   "ar-XA-Chirp3-HD-Charon",   # ذكر
    "nova":    "ar-XA-Chirp3-HD-Kore",     # أنثى
    "shimmer": "ar-XA-Chirp3-HD-Kore",     # أنثى
}

def _ai_speak_google(speakable: str, chat_id: int = 0, voice: str | None = None) -> bytes | None:
    """تحويل نص → صوت عربي أصيل باستخدام Google Cloud TTS مع SSML."""
    import requests, base64, html as _html
    key = os.getenv("GOOGLE_TTS_KEY", "")
    if not key:
        return None
    oai_voice    = voice or _tts_voice_per_user.get(chat_id, DEFAULT_TTS_VOICE)
    google_voice = _GOOGLE_VOICE_MAP.get(oai_voice, "ar-XA-Chirp3-HD-Charon")

    # ── تنظيف إضافي قبل SSML: إزالة أي حرف قد يكسر XML ─────────
    import re as _re
    clean = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', speakable)

    # ── بناء SSML: توقفات طبيعية تُحسّن الإيقاع والوضوح ─────────
    safe = _html.escape(clean)
    safe = safe.replace(". ",  '.<break time="300ms"/> ')
    safe = safe.replace("، ", '،<break time="120ms"/> ')
    safe = safe.replace("؟ ",  '؟<break time="320ms"/> ')
    safe = safe.replace("! ",  '!<break time="260ms"/> ')
    safe = safe.replace(": ",  ':<break time="180ms"/> ')
    ssml = f'<speak>{safe}</speak>'

    _voice_cfg = {"languageCode": "ar-XA", "name": google_voice}
    _audio_cfg = {
        "audioEncoding": "OGG_OPUS",
        "speakingRate":  0.96,
        # "pitch" محذوف — Chirp3-HD يرفضه (HTTP 400) فكانت كل الطلبات تفشل
        # effectsProfileId محذوف — غير متوافق مع Chirp3-HD ويسبب 400
    }
    # المفتاح في الترويسة وليس في الرابط — رسائل الخطأ تحوي الرابط وتُسجَّل وتُرسل كتنبيه
    url = "https://texttospeech.googleapis.com/v1/text:synthesize"

    def _post(input_payload):
        r = requests.post(url, headers={"X-Goog-Api-Key": key},
                          json={"input": input_payload,
                                "voice": _voice_cfg,
                                "audioConfig": _audio_cfg},
                          timeout=20)
        r.raise_for_status()
        return base64.b64decode(r.json()["audioContent"])

    # ① حاول SSML أولاً
    try:
        audio_bytes = _post({"ssml": ssml})
        logger.info(f"Google TTS ok (SSML): voice={google_voice} audio={len(audio_bytes)}")
        return audio_bytes
    except Exception as ssml_err:
        logger.warning(f"Google TTS SSML failed: {ssml_err} → retrying plain text")

    # ② fallback لـ plain text عند أي فشل في SSML
    try:
        audio_bytes = _post({"text": clean})
        logger.info(f"Google TTS ok (plain): voice={google_voice} audio={len(audio_bytes)}")
        return audio_bytes
    except Exception as plain_err:
        # فقط لو الاتنين فشلوا → أرسل تنبيه
        logger.warning(f"Google TTS failed (SSML+plain): {plain_err}")
        _track_error("Google TTS", str(plain_err)[:120])
        return None




def _ai_speak_gemini(speakable: str, chat_id: int = 0) -> bytes | None:
    """Arabic TTS using Gemini 2.5 Flash TTS — best Arabic quality."""
    try:
        from google import genai
        from google.genai import types
        import wave as _wave, io as _io, subprocess, tempfile, os as _os

        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return None

        _GEMINI_VOICE_MAP = {
            "onyx": "Charon", "echo": "Fenrir", "fable": "Puck",
            "nova": "Kore", "shimmer": "Aoede", "alloy": "Charon",
        }
        oai_voice    = _tts_voice_per_user.get(chat_id, DEFAULT_TTS_VOICE)
        gemini_voice = _GEMINI_VOICE_MAP.get(oai_voice, "Charon")

        client   = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=speakable,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=gemini_voice
                        )
                    )
                )
            )
        )

        part    = response.candidates[0].content.parts[0]
        pcm_raw = part.inline_data.data   # bytes, L16 PCM 24kHz mono

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wt:
            wav_path = wt.name
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as ot:
            ogg_path = ot.name

        try:
            with _wave.open(wav_path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(pcm_raw)

            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            proc = subprocess.run(
                [ffmpeg_exe, "-i", wav_path,
                 "-c:a", "libopus", "-b:a", "64k",
                 ogg_path, "-y", "-loglevel", "error"],
                capture_output=True, timeout=15
            )
            if proc.returncode == 0:
                with open(ogg_path, "rb") as f:
                    ogg_bytes = f.read()
                duration = len(pcm_raw) / 48000
                logger.info(f"Gemini TTS ok: voice={gemini_voice} size={len(ogg_bytes)}B duration={duration:.1f}s")
                return ogg_bytes
            else:
                logger.warning(f"ffmpeg conversion failed: {proc.stderr.decode()[:80]}")
                return None
        finally:
            _os.unlink(wav_path) if _os.path.exists(wav_path) else None
            _os.unlink(ogg_path) if _os.path.exists(ogg_path) else None

    except Exception as e:
        logger.warning(f"Gemini TTS failed: {e}")
        _track_error("Gemini TTS", str(e)[:120])
        return None



def _ai_speak(reply_text: str, chat_id: int = 0) -> bytes | None:
    """تحويل نص → صوت: Google Chirp3 (عربي أصيل) ← Gemini ← OpenAI كاحتياط."""
    speakable = _tts_prepare(reply_text)

    # ⓪ Google Cloud TTS — الأولوية (اختيار المالك 2026-09-23؛ أول مليون حرف شهرياً مجاناً)
    if os.getenv("GOOGLE_TTS_KEY"):
        audio = _ai_speak_google(speakable, chat_id)
        if audio:
            _last_voice_reply[chat_id] = audio
            return audio

    # ① Gemini TTS — الأولوية (عربي أصيل - أفضل جودة)
    if os.getenv("GEMINI_API_KEY"):
        audio = _ai_speak_gemini(speakable, chat_id)
        if audio:
            _last_voice_reply[chat_id] = audio
            return audio

    # ② OpenAI TTS — احتياط عند فشل Google
    if not AI_ENABLED:
        return None
    voice = _tts_voice_per_user.get(chat_id, DEFAULT_TTS_VOICE)
    try:
        import io
        response = _ai_client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=speakable,
            response_format="opus",
        )
        buf = io.BytesIO()
        for chunk in response.iter_bytes(chunk_size=4096):
            buf.write(chunk)
        audio_bytes = buf.getvalue()
        _last_voice_reply[chat_id] = audio_bytes
        return audio_bytes
    except Exception as e:
        logger.warning(f"OpenAI TTS failed: {e}")
        _track_error("OpenAI TTS", str(e)[:120])
        return None


_VOICE_RATE_LIMIT_SEC  = 8    # minimum seconds between voice messages per user

# ── Cache رسائل الخطأ الصوتية — تُولَّد مرة واحدة وتُحفَظ ───────
_voice_err_cache: dict[str, bytes | None] = {}

def _send_voice_error(cid: int, text: str):
    """أرسل رسالة خطأ صوتياً — مع cache للرسائل المتكررة."""
    import io
    # ابحث في الـ cache أولاً (لو نفس النص أُرسِل قبل كده)
    audio = _voice_err_cache.get(text)
    if audio is None:
        audio = _ai_speak(text, cid)
        if audio:
            _voice_err_cache[text] = audio   # احفظ للمرات القادمة
    if audio:
        buf = io.BytesIO(audio); buf.seek(0); buf.name = "err.ogg"
        try:
            bot.send_voice(cid, buf); return
        except Exception:
            pass
    bot.send_message(cid, text)   # fallback نصي
_VOICE_MIN_SIZE_BYTES  = 3000 # أقل من هذا = ضجيج أو صمت → تجاهل
_thinking_audio_cache: dict = {}  # voice_name → bytes (lazy-generated per voice)

def _get_thinking_audio(voice: str) -> bytes | None:
    """
    صوت 'لحظة من فضلك' يُرسَل فوراً بعد التفريغ.
    يستخدم Google TTS أولاً ثم OpenAI كاحتياط.
    يُولَّد مرة واحدة لكل صوت ويُخزَّن في الذاكرة.
    """
    if not AI_ENABLED:
        return None
    if voice not in _thinking_audio_cache:
        # بدون أي معالجة — النموذج العصبي ينطقها طبيعياً من غير تدخّل
        text = "لحظة من فضلك."
        # ⓪ Google ثم ① Gemini ثم ② OpenAI — نفس ترتيب الردود
        audio = _ai_speak_google(text, 0, voice=voice) if os.getenv("GOOGLE_TTS_KEY") else None
        if not audio and os.getenv("GEMINI_API_KEY"):
            audio = _ai_speak_gemini(text, 0)
        # ② OpenAI كاحتياط
        if not audio:
            try:
                import io
                resp = _ai_client.audio.speech.create(
                    model="tts-1", voice=voice,
                    input=text, response_format="opus",
                )
                buf = io.BytesIO()
                for chunk in resp.iter_bytes(4096): buf.write(chunk)
                audio = buf.getvalue()
            except Exception as e:
                logger.warning(f"Thinking audio generation failed: {e}")
                audio = None
        _thinking_audio_cache[voice] = audio
        if audio:
            logger.info(f"Thinking audio cached for voice '{voice}' ({len(audio)} bytes)")
    return _thinking_audio_cache.get(voice)


# _split_for_tts: moved to tts_text.py

def _send_voice_list(cid: int, user_text: str):
    """طلب قائمة بالصوت: القائمة كاملة نصاً + ملخص صوتي قصير — الاثنان من نفس استعلام القاعدة."""
    import io
    lst = voice_lists.build_list(user_text, db.db_path)
    for chunk in voice_lists.format_text(lst):
        bot.send_message(cid, chunk)                     # بلا parse_mode: العناوين قد تحوي * و _
    summary = voice_lists.voice_summary(lst, _dialect_per_user.get(cid, AI_DEFAULT_DIALECT))
    # في سجل المحادثة حتى يعرف المساعد السياق في السؤال التالي
    with _AI_LOCK:
        if cid not in _ai_history:
            _ai_history[cid] = _history_load(cid)
        _ai_history[cid] += [{"role": "user", "content": user_text},
                             {"role": "assistant", "content": summary}]
    _history_save(cid, "user", user_text)
    _history_save(cid, "assistant", summary)
    logger.info(f"Voice list: user={cid} items={len(lst['items'])} eng={lst['eng']} window={lst['window_label']}")
    audio = _ai_speak(summary, chat_id=cid)
    if audio:
        vbuf = io.BytesIO(audio); vbuf.name = "reply.ogg"
        bot.send_voice(cid, vbuf)
    else:
        bot.send_message(cid, summary)


_STT_HINTS_CACHE = {"at": 0.0, "text": ""}
_STT_HINTS_TTL_SEC = 600
_STT_MAX_OWNERS = 12


def _stt_prompt() -> str:
    """
    كلمات مساعدة لتحويل الصوت لنص: أسماء المهندسين والجهات المالكة النشطة من قاعدة البيانات
    (تتحدّث كل 10 دقائق) في أول القائمة، ثم مصطلحات المجال الثابتة.
    (2026-09-23) القائمة كانت ثابتة بلا أسماء — مع الضوضاء تحوّل "ناصف" إلى "ناصر".
    """
    now = time.time()
    if now - _STT_HINTS_CACHE["at"] > _STT_HINTS_TTL_SEC:
        hints = ""
        try:
            with db._get_connection() as conn:
                engs = [r[0] for r in conn.execute("SELECT name FROM engineers ORDER BY name").fetchall()]
                owners = [r[0] for r in conn.execute("""
                    SELECT TRIM(owner) FROM master_tenders
                    WHERE status NOT IN ('CLOSED','REJECTED') AND owner IS NOT NULL
                    GROUP BY TRIM(owner) ORDER BY COUNT(*) DESC""").fetchall()]
            # الجهات بالعربي فقط (الكلام عربي) وبطول معقول
            owners = [o for o in owners if o and any("؀" <= ch <= "ۿ" for ch in o)][:_STT_MAX_OWNERS]
            parts = []
            if engs:
                parts.append("المهندسين: " + "، ".join(engs))
            if owners:
                parts.append("الجهات: " + "، ".join(o[:40] for o in owners))
            hints = ". ".join(parts)
        except Exception as e:
            logger.debug(f"STT hints unavailable: {e}")
        _STT_HINTS_CACHE.update(at=now, text=hints)
    hints = _STT_HINTS_CACHE["text"]
    return (hints + ". " + WHISPER_DOMAIN_PROMPT) if hints else WHISPER_DOMAIN_PROMPT


@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    """
    Pipeline صوتي عالمي المستوى:
    1. فحص الحجم → رفض الضجيج فوراً
    2. Rate limiting
    3. Whisper + domain prompt + سياق المحادثة → دقة عالية
    4. إرسال "لحظة..." صوتياً → لا صمت مخيف
    5. GPT مختصر → TTS-HD
    6. تقسيم الرد الطويل → جزأين (تجاوب أسرع)
    """
    if not is_authorized(message): return
    if not AI_ENABLED:
        bot.send_message(message.chat.id, "⚠️ خاصية المساعد الذكي غير مفعّلة.")
        return

    cid = message.chat.id
    import io

    # ── 1. فحص حجم الصوت — رفض الضجيج ──────────────────────
    file_size = getattr(message.voice, 'file_size', 0) or 0
    if file_size < _VOICE_MIN_SIZE_BYTES:
        _send_voice_error(cid, "الرسالة قصيرة جداً. تحدث بوضوح وجرّب مرة أخرى.")
        return

    # ── 2. Rate limiting ──────────────────────────────────────
    now  = time.time()
    last = _voice_rate_limit.get(cid, 0)
    if now - last < _VOICE_RATE_LIMIT_SEC:
        remaining = int(_VOICE_RATE_LIMIT_SEC - (now - last))
        bot.send_message(cid, f"⏳ انتظر {remaining} ثانية.")
        return
    _voice_rate_limit[cid] = now

    try:
        bot.send_chat_action(cid, 'record_voice')

        # ── 3. تنزيل وتفريغ الصوت مع domain prompt ───────────
        finfo = bot.get_file(message.voice.file_id)
        raw   = bot.download_file(finfo.file_path)
        buf   = io.BytesIO(raw); buf.name = "voice.ogg"

        # سياق المحادثة السابقة يساعد Whisper على فهم الكلمات الغامضة
        hist = _ai_history.get(cid, [])
        last_exchange = ""
        if hist:
            for msg in reversed(hist[-4:]):
                if msg["role"] == "assistant":
                    last_exchange = msg["content"][:120]
                    break
        whisper_prompt = _stt_prompt()
        if last_exchange:
            whisper_prompt += f". السياق السابق: {last_exchange}"

        def _do_transcribe(audio_buf, prompt):
            audio_buf.seek(0)
            return _ai_client.audio.transcriptions.create(
                model=WHISPER_MODEL, file=audio_buf,
                language="ar", prompt=prompt,
            )

        transcript = _do_transcribe(buf, whisper_prompt)
        user_text  = (transcript.text or "").strip()

        # إعادة محاولة واحدة بـ prompt قصير جداً → يعطي Whisper حرية أكبر
        if not user_text:
            logger.info("Whisper returned empty — retrying with minimal prompt")
            buf2 = io.BytesIO(raw); buf2.name = "voice.ogg"
            transcript = _do_transcribe(buf2, "مناقصات، أرقام، تواريخ، دلوقتي")
            user_text  = (transcript.text or "").strip()

        if not user_text:
            _track_error("Whisper Empty", f"file_size={file_size}")
            _send_voice_error(cid, "لم أتمكن من فهم الرسالة. تحدث بوضوح وجرّب مرة أخرى.")
            return

        # ── 4. عرض ما سُمع + إرسال "لحظة..." فوراً ──────────
        bot.send_message(cid, f"🎤 *سمعت:* _{user_text}_", parse_mode="Markdown")

        # إرسال صوت "لحظة من فضلك" فيما يُحضَّر الرد الحقيقي
        voice_name = _tts_voice_per_user.get(cid, DEFAULT_TTS_VOICE)
        thinking   = _get_thinking_audio(voice_name)
        if thinking:
            tbuf = io.BytesIO(thinking); tbuf.name = "thinking.ogg"
            bot.send_voice(cid, tbuf)

        bot.send_chat_action(cid, 'record_voice')

        # ── 4b. طلب قائمة → القائمة نصاً من القاعدة + ملخص صوتي قصير (لا يكتبها الذكاء) ──
        if voice_lists.is_list_request(user_text):
            _send_voice_list(cid, user_text)
            return

        # ── 5. رد GPT مختصر ──────────────────────────────────
        reply = _ai_reply(cid, user_text, voice_mode=True)

        # ── 6. تقسيم وإرسال (جزء واحد أو جزآن بالتوازي) ────────
        parts = _split_for_tts(reply)
        if len(parts) == 2:
            # توليد الجزأين بالتوازي → أسرع بنسبة ~40%
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as _ex:
                _futs  = [_ex.submit(_ai_speak, p, cid) for p in parts]
                audios = [f.result() for f in _futs]
            for part, audio_bytes in zip(parts, audios):
                if audio_bytes:
                    vbuf = io.BytesIO(audio_bytes); vbuf.name = "reply.ogg"
                    bot.send_voice(cid, vbuf)
                else:
                    bot.send_message(cid, part)
        else:
            audio_bytes = _ai_speak(parts[0], chat_id=cid)
            if audio_bytes:
                vbuf = io.BytesIO(audio_bytes); vbuf.name = "reply.ogg"
                bot.send_voice(cid, vbuf)
            else:
                bot.send_message(cid, parts[0])

    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        _track_error("Voice Pipeline", str(e)[:120])   # ← تنبيه تلقائي
        bot.send_message(message.chat.id, f"⚠️ خطأ في معالجة الرسالة الصوتية.")


@bot.message_handler(func=lambda m: m.content_type == 'text' and not m.text.startswith('/'))
def handle_ai_text(message):
    """Catch-all: any non-command text → GPT reply (text or voice if voicemode on).
    Never reached in practice: handle_text_query (bot_commands) is registered first and
    takes all free text — it calls reply_with_ai() when it does not understand the question."""
    if not is_authorized(message): return
    reply_with_ai(message)


def reply_with_ai(message):
    """GPT reply to a free-text message (voice reply if the user enabled /voicemode)."""
    cid        = message.chat.id
    is_voice_m = cid in _voicemode_users

    bot.send_chat_action(cid, 'record_voice' if is_voice_m else 'typing')
    reply = _ai_reply(cid, message.text, voice_mode=is_voice_m)

    if is_voice_m:
        import io
        audio_bytes = _ai_speak(reply, chat_id=cid)
        if audio_bytes:
            vbuf = io.BytesIO(audio_bytes); vbuf.name = "reply.ogg"
            bot.send_voice(cid, vbuf)
            return
    bot.send_message(cid, reply)

