"""حسابات المهندسين: كلمة مؤقتة من الإدارة ← تغيير إلزامي ← دخول باسمه على اللوحة بصلاحيات مهامه فقط.
مهندس بلا حساب يدخل برمز البوابة المشترك كما كان (النور). (مهندسو النور وأسماء وهمية.)"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path

from db_manager import DBManager

import engineer_accounts as ea
import tasks_core
from tests.test_tasks_phase2 import add_tender, fresh_db


class AccountsCoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())

    def tearDown(self):
        self.conn.close()

    def test_lookup_does_not_create_table(self):
        self.assertIsNone(ea.verify(self.conn, "سعود", "x"))
        self.assertIsNone(self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='engineer_accounts'").fetchone())

    def test_issue_verify_change_disable(self):
        with self.assertRaises(LookupError):
            ea.issue(self.conn, "غير موجود")
        temp = ea.issue(self.conn, "سعود")
        self.assertRegex(temp, r"^[a-z2-9]{5}-[a-z2-9]{5}$")
        self.assertNotIn(temp, str(tuple(ea.get(self.conn, "سعود"))))          # hash فقط
        self.assertEqual(ea.verify(self.conn, "سعود", temp)["must_change"], 1)
        self.assertIs(ea.verify(self.conn, "سعود", "خطأ"), False)
        for cur, new, conf in ((temp, "short", "short"), ("wrong-pass", "Noor-2026!", "Noor-2026!"),
                               (temp, "Noor-2026!", "Noor-2026?"), (temp, temp, temp)):
            with self.subTest(new=new), self.assertRaises(ValueError):
                ea.change_password(self.conn, "سعود", cur, new, conf)
        ea.change_password(self.conn, "سعود", temp, "Noor-2026!", "Noor-2026!")
        self.assertIs(ea.verify(self.conn, "سعود", temp), False)
        self.assertEqual(ea.verify(self.conn, "سعود", "Noor-2026!")["must_change"], 0)
        ea.set_active(self.conn, "سعود", False)
        self.assertIs(ea.verify(self.conn, "سعود", "Noor-2026!"), False)


class PortalAndBoardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))
        import bp_engineer
        import company_profile
        import web_core
        import web_dashboard
        cls.bp, cls.cp, cls.wc, cls.app = bp_engineer, company_profile, web_core, web_dashboard.app
        for f in (web_dashboard.ensure_results_table, web_dashboard.ensure_tender_notes_table,
                  web_dashboard.ensure_app_config_table, web_dashboard.ensure_guarantees_table):
            f()
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            for n in ("يوسف", "فاطمه"):
                c.execute("INSERT OR IGNORE INTO engineers (name) VALUES (?)", (n,))
            tid = add_tender(c, "A-1", "تشجير ممشى تجريبي", "2026-12-10", "يوسف")
            tasks_core.ensure_tables(c)
            cls.mine = c.execute("INSERT INTO tender_tasks (tender_row_id, title, engineer) VALUES (?,?,?)",
                                 (tid, "زيارة الموقع", "يوسف")).lastrowid
            cls.other = c.execute("INSERT INTO tender_tasks (tender_row_id, title, engineer) VALUES (?,?,?)",
                                  (tid, "التسعير", "فاطمه")).lastrowid
            cls.tender = tid
            c.commit()

    def setUp(self):
        self._orig = (self.cp.PROFILE.get("features"), self.bp.ENGINEER_PIN)
        self.cp.PROFILE["features"] = ["kanban", "engineer_accounts"]
        self.bp.ENGINEER_PIN = "4321"
        self.wc._LOGIN_FAILS.clear()

    def tearDown(self):
        self.cp.PROFILE["features"], self.bp.ENGINEER_PIN = self._orig
        self.wc._LOGIN_FAILS.clear()

    def admin(self):
        cl = self.app.test_client()
        with cl.session_transaction() as s:
            s["admin_ok"] = True
        return cl

    def login(self, cl, name, pwd):
        return cl.post("/engineer", data={"name": name, "pin": pwd})

    def test_admin_page_gated(self):
        self.assertEqual(self.app.test_client().get("/admin/engineers").status_code, 302)
        self.assertIn("فريق المهندسين", self.admin().get("/admin/engineers").get_data(as_text=True))
        self.cp.PROFILE["features"] = ["kanban"]
        self.assertEqual(self.admin().get("/admin/engineers").status_code, 404)

    def test_full_journey(self):
        temp = self.admin().post("/admin/engineers/issue", json={"name": "يوسف"}).get_json()["temp_password"]
        eng = self.app.test_client()
        self.assertIn("غير صحيحة", self.login(eng, "يوسف", "4321").get_data(as_text=True))   # الرمز المشترك لم يعد يكفي
        r = self.login(eng, "يوسف", temp)
        self.assertTrue(r.headers["Location"].endswith("/engineer/password"))
        self.assertTrue(eng.get("/engineer/dashboard").headers["Location"].endswith("/engineer/password"))
        self.assertEqual(eng.get("/tasks").status_code, 302)                                   # قبل تغيير الكلمة
        r = eng.post("/engineer/password", data={"current": temp, "new": "Noor-Yousef-1", "confirm": "Noor-Yousef-1"})
        self.assertIn("تم تغيير كلمة المرور", r.get_data(as_text=True))
        self.assertEqual(eng.get("/engineer/dashboard").status_code, 200)

        page = eng.get("/tasks").get_data(as_text=True)
        self.assertIn('const ME = "\\u064a\\u0648\\u0633\\u0641"', page)
        self.assertTrue(eng.post(f"/api/tasks/{self.mine}/move", json={"status": "doing"}).get_json()["ok"])
        self.assertEqual(eng.post(f"/api/tasks/{self.other}/move", json={"status": "doing"}).status_code, 403)
        self.assertEqual(eng.post(f"/api/tasks/{self.other}", json={"notes": "x"}).status_code, 403)
        self.assertEqual(eng.post(f"/api/tasks/{self.mine}/delete").status_code, 403)
        self.assertEqual(eng.post(f"/api/tasks/{self.mine}/rating", json={"quality": 5, "commitment": 5}).status_code, 403)
        r = eng.post(f"/api/tasks/{self.mine}", json={"engineer": "فاطمه", "notes": "تمت المعاينة"}).get_json()
        self.assertEqual((r["task"]["engineer"], r["task"]["notes"]), ("يوسف", "تمت المعاينة"))
        created = eng.post("/api/tasks", json={"tender_row_id": self.tender, "title": "تقرير مصور",
                                               "engineer": "فاطمه"}).get_json()["task"]
        self.assertEqual(created["engineer"], "يوسف")
        acts = eng.get(f"/api/tasks/{self.mine}/activity").get_json()["activity"]
        self.assertEqual(acts[0]["actor"], "م. يوسف")
        code = eng.post("/engineer/telegram-code").get_json()
        self.assertRegex(code["code"], r"^\d{6}$")
        self.assertIn("ربط تليجرام", eng.get("/engineer/dashboard").get_data(as_text=True))
        self.assertTrue(eng.post("/engineer/telegram-unlink").get_json()["ok"])
        self.assertEqual(self.app.test_client().post("/engineer/telegram-code").status_code, 401)

    def test_login_switches_role_on_a_shared_browser(self):
        """دخول مهندس في متصفح عليه جلسة الإدارة/الفريق يبدّل الدور ولا يرث صلاحياتهما (2026-09-25)،
        والعكس: دخول الفريق أو الإدارة يُنهي هوية المهندس السابقة."""
        import web_auth
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as conn:
            conn.row_factory = sqlite3.Row
            temp = ea.issue(conn, "فاطمه")
            ea.change_password(conn, "فاطمه", temp, "Noor-Fatma-1", "Noor-Fatma-1")
            conn.commit()
        cl = self.admin()
        with cl.session_transaction() as s:
            s["ok"] = True
        self.login(cl, "فاطمه", "Noor-Fatma-1")
        self.assertEqual(cl.get("/admin/engineers").status_code, 302)                  # لا إدارة
        self.assertEqual(cl.get("/").status_code, 302)                                 # ولا دخول الفريق
        self.assertEqual(cl.post(f"/api/tasks/{self.mine}/delete").status_code, 403)   # صلاحيات المهندس فقط
        self.assertIn('const ME = "\\u0641\\u0627\\u0637\\u0645\\u0647"', cl.get("/tasks").get_data(as_text=True))
        cl.post("/login", data={"password": web_auth.DASH_PWD})
        with cl.session_transaction() as s:
            self.assertTrue(s.get("ok"))
            self.assertFalse(any(k.startswith("eng_") for k in s))

    def test_engineer_without_account_keeps_shared_pin(self):
        eng = self.app.test_client()
        r = self.login(eng, "فاطمه", "4321")
        self.assertTrue(r.headers["Location"].endswith("/engineer/dashboard"))
        self.assertEqual(eng.get("/tasks").status_code, 302)          # اللوحة للحسابات الشخصية فقط

    def test_lockout_after_repeated_failures(self):
        eng = self.app.test_client()
        for _ in range(5):
            self.login(eng, "فاطمه", "0000")
        self.assertIn("إيقاف المحاولات", self.login(eng, "فاطمه", "4321").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()


class RosterTest(unittest.TestCase):
    """إضافة مهندس معيَّن حديثاً وإزالة من ترك الشركة (إيقاف لا حذف) وإعادته."""

    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        self.conn.execute("CREATE TABLE engineer_subs (chat_id INTEGER PRIMARY KEY, engineer_name TEXT NOT NULL)")
        self.conn.execute("INSERT INTO engineer_subs VALUES (55, 'سعود')")

    def tearDown(self):
        self.conn.close()

    def names(self):
        return [r["name"] for r in ea.overview(self.conn) if r["employed"]]

    def test_add_validates_and_detects_duplicates(self):
        with self.assertRaises(ValueError):
            ea.add_engineer(self.conn, " ")
        self.assertEqual(ea.add_engineer(self.conn, "  خالد   العتيبي ", 7), "ADDED")
        self.assertIn("خالد العتيبي", self.names())
        self.assertEqual(ea.add_engineer(self.conn, "خالد العتيبي"), "EXISTS")

    def test_remove_keeps_history_closes_account_and_rehire(self):
        ea.issue(self.conn, "سعود")
        add_tender(self.conn, "R-1", "تجديد واجهات مبنى (تجريبي)", "2026-12-01", "سعود")
        left = ea.remove_engineer(self.conn, "سعود")
        self.assertEqual(left["open_tenders"], 1)
        self.assertNotIn("سعود", self.names())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM engineers WHERE name='سعود'").fetchone()[0], 1)
        self.assertEqual(ea.get(self.conn, "سعود")["active"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM engineer_subs").fetchone()[0], 0)
        self.assertEqual(ea.add_engineer(self.conn, "سعود"), "REACTIVATED")
        self.assertIn("سعود", self.names())
        with self.assertRaises(LookupError):
            ea.remove_engineer(self.conn, "غير موجود")


class TelegramLinkTest(unittest.TestCase):
    """ربط تليجرام بحساب المهندس: رمز من البوابة (مرة واحدة، 10 دقائق) بدل الرمز المشترك."""

    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        self.conn.execute("CREATE TABLE engineer_subs (chat_id INTEGER PRIMARY KEY, engineer_name TEXT NOT NULL, "
                          "subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    def tearDown(self):
        self.conn.close()

    def test_code_requires_account_and_binds_once(self):
        with self.assertRaises(LookupError):
            ea.issue_link_code(self.conn, "سعود")
        self.assertFalse(ea.pin_subscription_blocked(self.conn, "سعود"))
        ea.issue(self.conn, "سعود")
        self.assertTrue(ea.pin_subscription_blocked(self.conn, "سعود"))
        code = ea.issue_link_code(self.conn, "سعود")
        self.assertRegex(code, r"^\d{6}$")
        self.assertIsNone(ea.redeem_link_code(self.conn, "000000" if code != "000000" else "111111", 77))
        self.assertEqual(ea.redeem_link_code(self.conn, f" {code} ", 77), "سعود")
        self.assertEqual(ea.telegram_links(self.conn, "سعود"), 1)
        self.assertIsNone(ea.redeem_link_code(self.conn, code, 88))                    # مرة واحدة

    def test_new_code_replaces_old_and_expiry(self):
        ea.issue(self.conn, "تسنيم")
        old = ea.issue_link_code(self.conn, "تسنيم")
        new = ea.issue_link_code(self.conn, "تسنيم")
        if old != new:
            self.assertIsNone(ea.redeem_link_code(self.conn, old, 1))
        self.conn.execute("UPDATE telegram_link_codes SET expires_at=datetime('now','localtime','-1 minutes')")
        self.assertIsNone(ea.redeem_link_code(self.conn, new, 1))

    def test_password_reset_drops_old_subscriptions_and_unlink(self):
        self.conn.execute("INSERT INTO engineer_subs (chat_id, engineer_name) VALUES (5, 'فيصل')")    # قديم بالرمز المشترك
        ea.add_engineer(self.conn, "فيصل")
        ea.issue(self.conn, "فيصل")
        self.assertEqual(ea.telegram_links(self.conn, "فيصل"), 0)
        ea.redeem_link_code(self.conn, ea.issue_link_code(self.conn, "فيصل"), 9)
        self.assertEqual(ea.unlink_telegram(self.conn, "فيصل"), 1)
        self.assertEqual(ea.telegram_links(self.conn, "فيصل"), 0)
