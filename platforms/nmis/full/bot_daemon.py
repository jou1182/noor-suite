# -*- coding: utf-8 -*-
"""Telegram bot entry point: process lock, handler registration, scheduler, polling.

The bot was split into bot_core / bot_notifications / bot_commands / bot_callbacks /
bot_voice_ai / bot_jobs / bot_analytics on 2026-09-23 (behaviour unchanged)."""
import os
import sys
import threading
import time
from bot_core import BASE_DIR, LOG_DIR, bot, logger
from bot_jobs import schedule_runner

# Handler modules are imported in the original registration order — telebot tries
# handlers in that order, and the free-text/voice catch-alls must stay after the commands.
import bot_commands   # noqa: E402,F401
import bot_callbacks  # noqa: E402,F401
import bot_voice_ai   # noqa: E402,F401
import bot_analytics  # noqa: E402,F401



_lock_fd = None
def acquire_lock():
    global _lock_fd
    import tempfile, hashlib
    # اسم القفل مُشتق من مسار مجلد النسخة نفسها -- لو أكتر من مستأجر (tenant) شغّال
    # على نفس السيرفر، كل نسخة تراقب نفسها بس، مش تصادم نسخة تانية في مجلد مختلف
    _instance_id = hashlib.md5(str(BASE_DIR.resolve()).encode()).hexdigest()[:12]
    lock_file = os.path.join(tempfile.gettempdir(), f"tender_bot_{_instance_id}.lock")
    try:
        if os.name == 'nt':
            import msvcrt
            _lock_fd = os.open(lock_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
            msvcrt.locking(_lock_fd, msvcrt.LK_NBLCK, 1)
        else:
            if os.path.exists(lock_file):
                try:
                    with open(lock_file, "r") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, 0)  # raises ProcessLookupError if dead
                    # Process IS alive — exit cleanly (exit 0 = not an error, prevents systemd restart loop)
                    logger.info(f"Instance guard: bot already running (PID={pid}). This extra start will exit cleanly.")
                    sys.exit(0)
                except ProcessLookupError:
                    pass  # Old process is dead — safe to take over
                except (ValueError, FileNotFoundError):
                    pass  # Corrupt/missing lock file — proceed
            _lock_fd = open(lock_file, "w")
            _lock_fd.write(str(os.getpid()))
            _lock_fd.flush()
    except Exception as e:
        logger.error(f"FATAL: Lock acquisition error ({e})! Exiting.")
        sys.exit(1)

# ============================================================
# 8. ENTRY POINT
# ============================================================
if __name__ == "__main__":
    acquire_lock()
    logger.info("Starting Tender Bot Daemon - Professional Edition...")
    logger.info(f"Logs are being saved to: {LOG_DIR}")

    # Start background scheduler
    t = threading.Thread(target=schedule_runner, daemon=True)
    t.start()

    # Start Telegram polling with ISP-drop resilience
    logger.info("Bot is live and polling for Telegram callbacks...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            logger.warning(f"Telegram connection dropped. Reconnecting in 5s... ({e})")
            time.sleep(5)
