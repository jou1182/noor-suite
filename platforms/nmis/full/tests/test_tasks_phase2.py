"""لوحة المهام — المرحلة 2: قالب تلقائي لكل منافسة، مزامنة المراحل للأمام فقط، /mytasks وأزراره،
تذكير المتأخر، وإشعار الإسناد. (أسماء منافسات وهمية ومهندسو النور.)"""
from tests import _env  # noqa: F401  (قاعدة مؤقتة قبل استيراد المشروع)

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest import mock

from db_manager import DBManager

import tasks_core

TODAY = date(2026, 10, 1)


def fresh_db() -> Path:
    path = Path(tempfile.mkdtemp(prefix="noor_tests_tasks_")) / "t.db"
    DBManager(path)
    with closing(sqlite3.connect(path)) as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS tender_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, tender_id INTEGER UNIQUE,
                submitted_to_review INTEGER DEFAULT 0, submitted_to_upload INTEGER DEFAULT 0,
                uploaded_to_platform INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS tender_guarantees (tender_row_id INTEGER PRIMARY KEY, status TEXT DEFAULT 'PENDING');
        """)
        for name in ("سعود", "تسنيم"):
            c.execute("INSERT OR IGNORE INTO engineers (name) VALUES (?)", (name,))
        c.commit()
    return path


def add_tender(conn, key, title, deadline, engineer=None, status="InProgress") -> int:
    conn.execute("INSERT INTO master_tenders (tender_id, title, owner, submission_date, assigned_engineer, status) "
                 "VALUES (?,?,?,?,?,?)", (key, title, "جهة تجريبية", deadline, engineer, status))
    return conn.execute("SELECT id FROM master_tenders WHERE tender_id=?", (key,)).fetchone()[0]


def tasks_of(conn, tid) -> dict:
    return {r["template_key"]: r for r in conn.execute("SELECT * FROM tender_tasks WHERE tender_row_id=?", (tid,))}


class TemplateAndSyncTest(unittest.TestCase):
    def setUp(self):
        self.conn = tasks_core.connect(fresh_db())

    def tearDown(self):
        self.conn.close()

    def test_seed_once_with_engineer_and_back_scheduled_dues(self):
        tid = add_tender(self.conn, "N-1", "إنشاء مدرسة نموذجية بحي الورود", "20/10/2026", "سعود")
        closed = add_tender(self.conn, "N-2", "صيانة حديقة عامة", "2026-10-30", status="CLOSED")
        notices = tasks_core.refresh(self.conn, TODAY)
        t = tasks_of(self.conn, tid)
        self.assertEqual(set(t), {k for k, *_ in tasks_core.TEMPLATE})
        self.assertEqual({r["engineer"] for r in t.values()}, {"سعود"})
        self.assertEqual(t["upload"]["due_date"], "2026-10-19")      # يوم قبل الإغلاق (DD/MM/YYYY)
        self.assertEqual(t["study"]["due_date"], "2026-10-08")
        self.assertEqual(tasks_of(self.conn, closed), {})
        self.assertEqual([e for e, _ in notices], ["سعود"])

        self.conn.execute("DELETE FROM tender_tasks WHERE id=?", (t["site"]["id"],))
        self.assertEqual(tasks_core.refresh(self.conn, TODAY), [])
        self.assertNotIn("site", tasks_of(self.conn, tid))           # الحذف لا يُعاد إنشاؤه

    def test_due_never_before_today_unless_deadline_passed(self):
        soon = add_tender(self.conn, "N-3", "توريد أثاث مكتبي", "2026-10-03")
        past = add_tender(self.conn, "N-4", "تشجير طريق فرعي", "2026-09-20")
        tasks_core.refresh(self.conn, TODAY)
        self.assertEqual(tasks_of(self.conn, soon)["study"]["due_date"], "2026-10-01")
        self.assertEqual(tasks_of(self.conn, past)["study"]["due_date"], "2026-09-20")

    def test_stages_push_forward_only(self):
        tid = add_tender(self.conn, "N-5", "إنارة ممشى الحي", "2026-10-25", "تسنيم")
        tasks_core.refresh(self.conn, TODAY)
        t = tasks_of(self.conn, tid)
        tasks_core.move(self.conn, t["upload"]["id"], "done", "الإدارة")          # إنسان سبق النظام

        self.conn.execute("INSERT INTO tender_notes (tender_id, submitted_to_review) VALUES (?,1)", (tid,))
        tasks_core.refresh(self.conn, TODAY)
        t = tasks_of(self.conn, tid)
        self.assertEqual(t["review"]["status"], "doing")

        self.conn.execute("UPDATE tender_notes SET submitted_to_upload=1 WHERE tender_id=?", (tid,))
        self.conn.execute("INSERT INTO tender_guarantees (tender_row_id, status) VALUES (?, 'READY')", (tid,))
        tasks_core.refresh(self.conn, TODAY)
        t = tasks_of(self.conn, tid)
        self.assertEqual((t["review"]["status"], t["guarantee"]["status"]), ("done", "done"))
        self.assertTrue(t["review"]["done_at"])
        self.assertEqual(t["upload"]["status"], "done")                           # لم تُرجَع إلى doing
        acts = [r[0] for r in self.conn.execute(
            "SELECT actor FROM task_activity WHERE task_id=? AND action='move'", (t["review"]["id"],))]
        self.assertEqual(acts, [tasks_core.SYSTEM_ACTOR] * 2)

    def test_late_engineer_assignment_fills_template_tasks(self):
        tid = add_tender(self.conn, "N-6", "ترميم مركز صحي", "2026-10-28")
        tasks_core.refresh(self.conn, TODAY)
        self.assertEqual({r["engineer"] for r in tasks_of(self.conn, tid).values()}, {""})
        self.conn.execute("UPDATE master_tenders SET assigned_engineer='تسنيم' WHERE id=?", (tid,))
        notices = tasks_core.refresh(self.conn, TODAY)
        self.assertEqual({r["engineer"] for r in tasks_of(self.conn, tid).values()}, {"تسنيم"})
        self.assertEqual(len(notices), 1)
        self.assertIn("7 مهمة", notices[0][1])

    def test_overdue_by_engineer(self):
        tid = add_tender(self.conn, "N-7", "تمديد شبكة ري", "2026-09-25", "سعود")
        tasks_core.refresh(self.conn, TODAY)
        late = tasks_core.overdue_by_engineer(self.conn, TODAY)
        self.assertEqual(len(late["سعود"]), len(tasks_core.TEMPLATE))
        for r in tasks_of(self.conn, tid).values():
            tasks_core.move(self.conn, r["id"], "done", "الإدارة")
        self.assertEqual(tasks_core.overdue_by_engineer(self.conn, TODAY), {})


class BotTasksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
        os.environ.setdefault("CHAT_ID", "-100")
        os.environ.setdefault("BOT_LOG_DIR", tempfile.mkdtemp(prefix="noor_tests_logs_"))
        import bot_tasks
        import company_profile
        cls.bt, cls.cp = bot_tasks, company_profile

    def setUp(self):
        self.db = fresh_db()
        self._orig = (self.bt.DB_PATH, self.cp.PROFILE.get("features"))
        self.bt.DB_PATH = self.db
        self.cp.PROFILE["features"] = ["kanban"]
        with closing(tasks_core.connect(self.db)) as c:
            self.tid = add_tender(c, "N-8", "إنشاء ملعب رياضي", "2026-09-28", "سعود")
            c.execute("CREATE TABLE engineer_subs (chat_id INTEGER PRIMARY KEY, engineer_name TEXT NOT NULL)")
            c.execute("INSERT INTO engineer_subs VALUES (111, 'سعود'), (222, 'تسنيم')")
            tasks_core.refresh(c, TODAY)
            c.commit()
            self.study = tasks_of(c, self.tid)["study"]["id"]

    def tearDown(self):
        self.bt.DB_PATH, self.cp.PROFILE["features"] = self._orig

    def test_mytasks_lists_open_tasks_with_buttons(self):
        text, markup = self.bt.my_tasks_message("سعود")
        self.assertIn("إنشاء ملعب رياضي", text)
        self.assertIn(f"tsk_{self.study}_doing", str(markup.to_dict()))
        self.assertIsNone(self.bt.my_tasks_message("تسنيم")[1])

    def test_button_only_moves_own_task(self):
        with mock.patch.object(self.bt, "_push_board_refresh"):
            self.assertIn("ليست مسندة", self.bt.apply_button("تسنيم", self.study, "done"))
            self.assertIn("أُنجزت", self.bt.apply_button("سعود", self.study, "done"))
        with closing(tasks_core.connect(self.db)) as c:
            self.assertEqual(c.execute("SELECT status FROM tender_tasks WHERE id=?", (self.study,)).fetchone()[0], "done")
            actor = c.execute("SELECT actor FROM task_activity WHERE task_id=? ORDER BY id DESC", (self.study,)).fetchone()[0]
        self.assertEqual(actor, "م. سعود (تليجرام)")

    def test_reminders_go_to_engineer_and_group(self):
        with mock.patch.object(self.bt.bot, "send_message") as send, mock.patch.object(self.bt, "is_paused", return_value=False):
            self.bt.job_task_reminders(TODAY)
        chats = [call.args[0] for call in send.call_args_list]
        self.assertIn(111, chats)
        self.assertNotIn(222, chats)
        self.assertEqual(len(chats), 2)                                   # المهندس + ملخص المجموعة

    def test_disabled_instance_does_nothing(self):
        self.cp.PROFILE["features"] = []
        with mock.patch.object(self.bt.bot, "send_message") as send:
            self.bt.job_task_reminders(TODAY)
            self.bt.after_cycle()
        send.assert_not_called()


class DashboardHooksTest(unittest.TestCase):
    """حفظ علامات المنافسة من اللوحة يحرّك مهام القالب، والإسناد يرسل إشعاراً خاصاً للمشترك."""

    @classmethod
    def setUpClass(cls):
        DBManager(Path(os.environ["DB_PATH"]))
        import company_profile
        import web_dashboard
        import web_tasks
        cls.cp, cls.wt, cls.app = company_profile, web_tasks, web_dashboard.app
        web_dashboard.ensure_tender_notes_table()
        with closing(sqlite3.connect(os.environ["DB_PATH"])) as c:
            c.execute("INSERT OR IGNORE INTO engineers (name) VALUES ('تسنيم')")
            c.execute("CREATE TABLE IF NOT EXISTS engineer_subs (chat_id INTEGER PRIMARY KEY, engineer_name TEXT NOT NULL)")
            c.execute("INSERT OR IGNORE INTO engineer_subs VALUES (333, 'تسنيم')")
            cls.tid = add_tender(c, "N-9", "بناء سور مدرسة", "2026-12-15", "تسنيم")
            c.commit()

    def setUp(self):
        self._orig = self.cp.PROFILE.get("features")
        self.cp.PROFILE["features"] = ["kanban"]
        self.client = self.app.test_client()
        with self.client.session_transaction() as s:
            s["ok"] = True

    def tearDown(self):
        self.cp.PROFILE["features"] = self._orig

    def _tasks(self):
        self.client.get("/tasks")                                  # فتح اللوحة يجهّز قوالب المنافسات الجديدة
        return {t["template_key"]: t for t in self.client.get(f"/api/tasks?tender={self.tid}").get_json()["tasks"]}

    def test_notes_save_moves_review_task(self):
        self.assertEqual(self._tasks()["review"]["status"], "todo")
        r = self.client.post(f"/api/tender/{self.tid}/notes", json={"submitted_to_review": True})
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(self._tasks()["review"]["status"], "doing")

    def test_assignment_sends_private_notice(self):
        with mock.patch.object(self.wt, "_send_telegram_dm", return_value=True) as dm, \
             mock.patch.object(self.wt.threading, "Thread") as th:
            th.side_effect = lambda target, daemon: mock.Mock(start=target)
            r = self.client.post("/api/tasks", json={"tender_row_id": self.tid, "title": "إعداد جدول زمني",
                                                     "engineer": "تسنيم", "due_date": "2026-12-01"})
        self.assertTrue(r.get_json()["ok"])
        dm.assert_called_once()
        self.assertEqual(dm.call_args.args[0], "333")
        self.assertIn("إعداد جدول زمني", dm.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
