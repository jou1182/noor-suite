# -*- coding: utf-8 -*-
"""Noor Tender Monitor — Web Dashboard entry point.

Split on 2026-09-23 into web_core / web_auth / web_data / web_admin / web_api / web_pages;
every module registers its routes on the same Flask app, so URLs and endpoint names are unchanged."""
from web_core import PORT, app, ensure_app_config_table, ensure_guarantees_table, ensure_results_table, ensure_tender_notes_table
# Route modules: importing them registers their routes on `app`.
import web_auth   # noqa: F401
import web_admin  # noqa: F401
import web_api    # noqa: F401
import web_pages  # noqa: F401
import web_tasks  # noqa: F401  (لوحة المهام — تعمل فقط مع features: kanban)
import web_accounts  # noqa: F401  (حسابات المهندسين — تعمل فقط مع features: engineer_accounts)
import web_analytics  # noqa: F401  (التحليلات — تعمل فقط مع features: analytics)
import web_source  # noqa: F401  (مصدر المنافسات — فقط لنسخ الإدخال اليدوي portal_adapter: manual)
import web_demo  # noqa: F401  (وضع العرض — features: demo)
import web_calendar  # noqa: F401  (التقويم — features: calendar)
import web_task_templates  # noqa: F401  (قوالب المهام — مع لوحة المهام)
import web_viewer  # noqa: F401  (حساب العرض للطلاب — مع features: demo)
# Re-exported for tests/tools that used to import them from here.
from web_core import DB_PATH, VERSION, ensure_app_config_table, ensure_guarantees_table, ensure_results_table, ensure_tender_notes_table  # noqa: F401,E402

# ══════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════

from bp_engineer import bp_engineer
app.register_blueprint(bp_engineer)

if __name__ == "__main__":
    ensure_results_table()
    ensure_tender_notes_table()
    ensure_app_config_table()
    ensure_guarantees_table()
    app.run(host="127.0.0.1", port=PORT, debug=False)
