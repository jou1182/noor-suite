"""
خريطة مسارات لوحة التحكم + سلوك تغيير كلمة المرور.

اللقطة مأخوذة من web_dashboard.py قبل تقسيمه (2026-09-23): كل مسار (URL، اسم endpoint،
الطرق). أي تغيير يجب أن يكون مقصوداً — حدّث القائمة هنا عندها.
"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import tempfile
import unittest
from pathlib import Path

EXPECTED_ROUTES = [
    ('/', 'dashboard', ('GET',)),
    ('/admin', 'admin_panel', ('GET',)),
    ('/admin/change-admin-password', 'admin_change_admin_password', ('POST',)),
    ('/admin/change-password', 'admin_change_password', ('POST',)),
    ('/admin/db-backup', 'admin_db_backup', ('GET',)),
    ('/admin/demo', 'admin_demo', ('GET',)),
    ('/admin/demo/clear', 'admin_demo_clear', ('POST',)),
    ('/admin/demo/nightly', 'admin_demo_nightly', ('POST',)),
    ('/admin/demo/seed', 'admin_demo_seed', ('POST',)),
    ('/admin/demo/viewer', 'admin_demo_viewer', ('POST',)),
    ('/admin/engineers', 'admin_engineers', ('GET',)),
    ('/admin/engineers/active', 'admin_engineers_active', ('POST',)),
    ('/admin/engineers/add', 'admin_engineers_add', ('POST',)),
    ('/admin/engineers/issue', 'admin_engineers_issue', ('POST',)),
    ('/admin/engineers/remove', 'admin_engineers_remove', ('POST',)),
    ('/admin/source', 'admin_source', ('GET',)),
    ('/admin/task-templates', 'admin_task_templates', ('GET',)),
    ('/admin/source/apply', 'admin_source_apply', ('POST',)),
    ('/admin/source/file.xlsx', 'admin_source_download', ('GET',)),
    ('/admin/source/preview', 'admin_source_preview', ('POST',)),
    ('/admin/source/settings', 'admin_source_settings', ('POST',)),
    ('/admin/source/template.xlsx', 'admin_source_template', ('GET',)),
    ('/admin/forgot', 'admin_forgot', ('GET', 'POST')),
    ('/admin/knowledge', 'admin_knowledge_list', ('GET',)),
    ('/admin/knowledge/delete', 'admin_knowledge_delete', ('POST',)),
    ('/admin/knowledge/read', 'admin_knowledge_read', ('GET',)),
    ('/admin/knowledge/reload', 'admin_knowledge_reload', ('POST',)),
    ('/admin/knowledge/save', 'admin_knowledge_save', ('POST',)),
    ('/admin/login', 'admin_login', ('GET', 'POST')),
    ('/admin/logout', 'admin_logout', ('GET',)),
    ('/admin/reset-logo', 'admin_reset_logo', ('POST',)),
    ('/admin/save-identity', 'admin_save_identity', ('POST',)),
    ('/admin/upload-logo', 'admin_upload_logo', ('POST',)),
    ('/analytics', 'analytics_page', ('GET',)),
    ('/calendar', 'calendar_page', ('GET',)),
    ('/analytics/export.csv', 'analytics_export', ('GET',)),
    ('/api/admin/tender/<int:tid>/status', 'api_admin_update_status', ('POST',)),
    ('/api/analytics', 'api_analytics', ('GET',)),
    ('/api/calendar', 'api_calendar', ('GET',)),
    ('/api/task-templates', 'api_task_templates', ('GET',)),
    ('/api/task-templates', 'api_task_templates_save', ('POST',)),
    ('/api/task-templates/delete', 'api_task_templates_delete', ('POST',)),
    ('/api/analytics/compare', 'api_analytics_compare', ('GET',)),
    ('/api/bulk_assign', 'api_bulk_assign', ('POST',)),
    ('/api/eng/tender/<int:tid>/status', 'engineer.api_eng_update_status', ('POST',)),
    ('/api/pending/<int:pending_id>/approve', 'api_approve_pending', ('POST',)),
    ('/api/notifications', 'api_notifications', ('GET',)),
    ('/api/notifications/read', 'api_notifications_read', ('POST',)),
    ('/api/push-event', 'api_push_event', ('POST',)),
    ('/api/result-rec/<int:rec_id>/quick', 'api_result_quick', ('POST',)),
    ('/api/result/<int:row_id>', 'api_get_result', ('GET',)),
    ('/api/result/<int:row_id>/save', 'api_save_result', ('POST',)),
    ('/api/stats', 'api_stats', ('GET',)),
    ('/api/stream', 'sse_stream', ('GET',)),
    ('/api/tasks', 'api_tasks_create', ('POST',)),
    ('/api/tasks', 'api_tasks_list', ('GET',)),
    ('/api/tasks/<int:task_id>', 'api_tasks_update', ('POST',)),
    ('/api/tasks/<int:task_id>/activity', 'api_tasks_activity', ('GET',)),
    ('/api/tasks/<int:task_id>/delete', 'api_tasks_delete', ('POST',)),
    ('/api/tasks/<int:task_id>/move', 'api_tasks_move', ('POST',)),
    ('/api/tasks/<int:task_id>/rating', 'api_tasks_rate', ('POST',)),
    ('/api/team', 'api_team', ('GET',)),
    ('/api/tender/<int:row_id>', 'api_get_tender', ('GET',)),
    ('/api/tender/<int:row_id>/guarantee', 'api_tender_guarantee', ('GET', 'POST')),
    ('/api/tender/<int:row_id>/notes', 'api_save_notes', ('POST',)),
    ('/api/tender/<int:row_id>/toggle-date-lock', 'api_toggle_date_lock', ('POST',)),
    ('/api/tender/<int:row_id>/toggle-lock', 'api_toggle_engineer_lock', ('POST',)),
    ('/api/tender/<int:row_id>/update', 'api_update_tender', ('POST',)),
    ('/engineer', 'engineer.engineer_home', ('GET', 'POST')),
    ('/engineer-view', 'engineer_view', ('GET',)),
    ('/engineer/dashboard', 'engineer.engineer_dashboard', ('GET',)),
    ('/engineer/logout', 'engineer.engineer_logout', ('GET',)),
    ('/engineer/password', 'engineer.engineer_password', ('GET', 'POST')),
    ('/engineer/telegram-code', 'engineer.engineer_telegram_code', ('POST',)),
    ('/engineer/telegram-unlink', 'engineer.engineer_telegram_unlink', ('POST',)),
    ('/export/csv', 'export_csv', ('GET',)),
    ('/forgot', 'dash_forgot', ('GET', 'POST')),
    ('/healthz', 'healthz', ('GET',)),
    ('/login', 'login', ('GET', 'POST')),
    ('/logo', 'serve_logo', ('GET',)),
    ('/logout', 'logout', ('GET',)),
    ('/owners', 'owners_page', ('GET',)),
    ('/results', 'results_page', ('GET',)),
    ('/static/<path:filename>', 'static', ('GET',)),
    ('/tasks', 'tasks_page', ('GET',)),
    ('/team', 'team_page', ('GET',)),
    ('/team/report.pdf', 'team_report_pdf', ('GET',)),
    ('/tender/<int:row_id>', 'tender_detail', ('GET',)),
    ('/viewer', 'viewer_login', ('GET', 'POST')),
]
EXPECTED_HOOKS = {'before': ['block_direct_ip_access', 'session_idle_guard', 'viewer_read_only'], 'after': ['_no_html_cache', '_apply_palette', 'viewer_banner'], 'ctx': ['_default_template_ctx_processor', '_inject_company', '_kanban_nav'], 'blueprints': ['engineer']}


class DashboardRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import web_dashboard
        cls.app = web_dashboard.app

    def test_route_map_unchanged(self):
        got = sorted((r.rule, r.endpoint, tuple(sorted(r.methods - {"HEAD", "OPTIONS"})))
                     for r in self.app.url_map.iter_rules())
        self.assertEqual(got, sorted(EXPECTED_ROUTES))

    def test_request_hooks_unchanged(self):
        got = {
            "before": [f.__name__ for f in self.app.before_request_funcs.get(None, [])],
            "after": [f.__name__ for f in self.app.after_request_funcs.get(None, [])],
            "ctx": [f.__name__ for f in self.app.template_context_processors.get(None, [])],
            "blueprints": sorted(self.app.blueprints),
        }
        self.assertEqual(got, EXPECTED_HOOKS)


class PasswordChangeTakesEffectTest(unittest.TestCase):
    """DASH_PWD يُعاد ربطه بـ global — يجب أن يبقى مع دالة الدخول في نفس الوحدة (web_auth)."""

    def setUp(self):
        import web_auth
        import web_dashboard
        self.wa = web_auth
        self.client = web_dashboard.app.test_client()
        self.tmp_env = Path(tempfile.mkdtemp(prefix="noor_tests_env_")) / ".env"
        self.tmp_env.write_text("DASHBOARD_PASSWORD=oldpass1" + chr(10), encoding="utf-8")
        self._orig = (web_auth.ENV_PATH, web_auth.DASH_PWD)
        web_auth.ENV_PATH = str(self.tmp_env)   # لا يلمس .env الحقيقي أبداً
        web_auth.DASH_PWD = "oldpass1"

    def tearDown(self):
        self.wa.ENV_PATH, self.wa.DASH_PWD = self._orig

    def login(self, pwd):
        return self.client.post("/login", data={"password": pwd})

    def test_new_password_works_immediately_without_restart(self):
        self.assertEqual(self.login("oldpass1").status_code, 302)
        with self.client.session_transaction() as s:
            s["admin_ok"] = True
        r = self.client.post("/admin/change-password", data={"new_pwd": "newpass99", "new_pwd2": "newpass99"})
        self.assertTrue(r.get_json()["ok"])
        self.assertIn("DASHBOARD_PASSWORD=newpass99", self.tmp_env.read_text(encoding="utf-8"))
        self.assertEqual(self.login("newpass99").status_code, 302)   # نجاح = تحويل للوحة
        self.assertEqual(self.login("oldpass1").status_code, 200)    # القديمة مرفوضة


if __name__ == "__main__":
    unittest.main()
