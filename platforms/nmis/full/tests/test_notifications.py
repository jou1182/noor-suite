"""جرس الإشعارات: من سجل نشاط المهام، لكل مشاهد ما يخصه، وحالة قراءة مستقلة، و«مطلوب منك الآن».
التقييم للإدارة فقط. (أسماء وهمية ومهندسو النور.)"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import unittest
from datetime import date

import tasks_core
from tests.test_tasks_phase2 import add_tender, fresh_db

TODAY = date(2026, 10, 10)


class NotificationsTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())
        tasks_core.ensure_tables(self.conn)
        tid = add_tender(self.conn, "N-1", "تشجير ساحة عامة (تجريبي)", "2026-10-30", "سعود")
        ins = "INSERT INTO tender_tasks (tender_row_id, title, engineer, status, due_date, done_at) VALUES (?,?,?,?,?,?)"
        self.mine = self.conn.execute(ins, (tid, "زيارة الموقع", "سعود", "todo", "2026-10-05", "")).lastrowid
        self.done = self.conn.execute(ins, (tid, "الضمان", "تسنيم", "done", "2026-10-01", "2026-10-01")).lastrowid
        log = tasks_core.log
        log(self.conn, self.mine, "move", "نُقلت إلى «قيد التنفيذ»", "الإدارة")        # لسعود من غيره
        log(self.conn, self.mine, "edit", "عُدّلت: الملاحظات", "م. سعود")              # من سعود نفسه
        log(self.conn, self.done, "move", "نُقلت إلى «منتهية»", "م. تسنيم (تليجرام)")
        tasks_core.rate(self.conn, self.done, 5, 4, "", "الإدارة")

    def tearDown(self):
        self.conn.close()

    def feed(self, viewer):
        return tasks_core.notifications(self.conn, viewer, today=TODAY)

    def test_each_viewer_sees_what_concerns_them(self):
        eng = self.feed("eng:سعود")
        self.assertEqual([i["actor"] for i in eng["items"]], ["الإدارة"])           # لا أفعاله هو
        admin = self.feed("admin")
        self.assertEqual([i["actor"] for i in admin["items"]], ["م. تسنيم (تليجرام)", "م. سعود"])   # الأحدث أولاً
        team = self.feed("team")
        self.assertNotIn("rate", [i["action"] for i in team["items"]])              # التقييم للإدارة فقط
        self.assertNotIn("rate", [i["action"] for i in eng["items"]])

    def test_unread_and_mark_read_per_viewer(self):
        self.assertEqual(self.feed("team")["unread"], 3)
        tasks_core.mark_notifications_read(self.conn, "team")
        self.assertEqual(self.feed("team")["unread"], 0)
        self.assertEqual(self.feed("admin")["unread"], 2)                            # مستقل لكل مشاهد
        tasks_core.log(self.conn, self.mine, "edit", "عُدّلت: الملاحظات", "م. سعود")
        self.assertEqual(self.feed("team")["unread"], 1)

    def test_required_now(self):
        self.conn.execute("DELETE FROM task_ratings")
        admin = [r["kind"] for r in self.feed("admin")["required"]]
        self.assertEqual(admin, ["rate", "late"])                                    # منتهية بلا تقييم + متأخرة
        eng = self.feed("eng:سعود")["required"]
        self.assertEqual([(r["kind"], r["task_id"]) for r in eng], [("late", self.mine)])
        self.assertEqual(self.feed("eng:تسنيم")["required"], [])


if __name__ == "__main__":
    unittest.main()


class SystemNoiseTest(unittest.TestCase):
    def test_template_creation_is_quiet_for_admin_but_not_for_engineer(self):
        conn = tasks_core.connect(fresh_db())
        add_tender(conn, "Q-1", "إنارة ممر (تجريبي)", "2026-12-01", "سعود")
        tasks_core.refresh(conn, TODAY)                                     # 7 مهام قالب + إسناد
        self.assertEqual(tasks_core.notifications(conn, "admin", today=TODAY)["unread"], 0)
        self.assertEqual(tasks_core.notifications(conn, "eng:سعود", today=TODAY)["unread"], 14)
        conn.close()
