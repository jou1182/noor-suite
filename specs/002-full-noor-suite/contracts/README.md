# عقود المنظومة الكاملة (`noor.*/v1`) — إضافة على عقود 001

مخططات JSON Schema (draft 2020-12)، `additionalProperties: false`. أُنشئت وفُحصت بـ `jsonschema` (`check_schema` + عينات قبول ورفض) في 2026-10-27، وعُدّلت بعد نقد Codex الجولة 1. لا تحمل أي قيمة معرّف الجلسة أو تجزيئه، ورمز CSRF في حقل `csrf` بقيمة عشوائية فقط.

**شرط قبل الاستعمال (نقد Codex، الملاحظة 4):** مُتحقِّق 001 (`packages/noor_contracts/validate.py`) يحصر الأسماء اليوم في عقود 001 الستة، وكشف المسارات فيه لا يلتقط كل المسارات المطلقة (مثل `/etc/...`). لذلك تتضمن المهام: (1) تسجيل العقود العشرة (التسعة + `open-approval`) في المُتحقِّق؛ (2) توسيع قاعدة 1 لتكشف أي مسار مطلق POSIX (`^/[^/]`) وUNC وحرف قرص و`file:`، مع استثناء صريح لحقول URL المسموحة فقط (`provider-config.endpoint`)؛ (3) اختبار مُنتِج ومستهلك لكل عقد. **حكم الامتثال للمبدأ VI في الخطة مشروط بنجاحها.**

| العقد | المُنتِج ← المستهلك | المتطلبات | research |
|---|---|---|---|
| [principal](principal.schema.json) | البيت (الوكيل) ← خادم كل منصة: حمولة `X-Noor-Assertion` الموقّعة Ed25519 بمفتاح البيت | FR-002، FR-003، FR-005 | R2 |
| [authz-decision](authz-decision.schema.json) | البيت ← منصة (فعل على منافسة) | المبدأ I، FR-005 | R2 |
| [desktop-event](desktop-event.schema.json) | البيت ← ATPAS (long-poll) | FR-002 (قفل ≤5 ث) | R3 |
| [platform-status](platform-status.schema.json) | البيت ← الغلاف وحساب العرض | FR-001، FR-028، SC-011 | — |
| [provider-config](provider-config.schema.json) | إعداد ← كل منصة بنموذج | FR-014، FR-015، US5 | R8 |
| [identity-profile](identity-profile.schema.json) | إعداد ← الخمس ومخرجاتها | FR-020..022، US4 | R9 |
| [labels](labels.schema.json) | ثابت في الكود ← الخمس | FR-023، FR-024 | R9 |
| [snapshot-manifest](snapshot-manifest.schema.json) | أداة التجهيز ← المستودع | FR-007، SC-005 | R4 |
| [qa-analysis](qa-analysis.schema.json) | التحليل السريع ← البيت | QA-U6، FR-013 | R7 |
| [open-approval](open-approval.schema.json) | إطار JoUReady ← غلاف البيت (`postMessage`، انتقال فقط) | المبدأ I، JR-D0، FR-010 (JR-F03) | R2، internal-api §4 (أُضيف 2026-10-27 بعد `/speckit.analyze`) |

ملاحق غير مخططة:
- [internal-api.md](internal-api.md) — التأكيد الموقّع، و`authz/check`، ونقاط ATPAS المكتبية (الملاحظتان 1 و2).
- [surfaces.md](surfaces.md) — كتالوج الأسطح المفحوصة (FR-030).
- [fr010-checklists.md](fr010-checklists.md) — قوائم الوظائف بمعرّفات البنود (FR-010، SC-002).

## قواعد فوق المخطط (يفرضها المستهلك)

1. **principal**: لا يُقبل إلا داخل تأكيد موقّع صالح (internal-api §1): توقيع البيت بالمفتاح العام، و`platform_id` = المنصة، والعمر ≤5 ثوانٍ، و`nonce` فريد لكل تأكيد ولمرة واحدة عند المنصة؛ ربطه بالجلسة في البيت فقط ويُتحقق منه عند `authz/check`. لا معرّف جلسة ولا مرجع ثابت لها في العقد.
2. **provider-config**: في بناء الهاكاثون يُرفض `mode: cloud` **قبل** قراءة `consent`. وفي بناء العميل يُتحقق من `signature_ed25519` على تسلسل قانوني للحقول بمفتاح العميل العام. أكثر من ملف `cloud` واحد في التثبيت ⇒ فشل البدء.
3. **platform-status**: `demo_gate = passed` يتطلب `fr010.passed = fr010.total` بنتيجة FR010Run كاملة الأدلة، وقرار بوابة مسجّلًا، وكتالوج أسطح معتمدًا (R11، R13).
4. **identity-profile**: كل ملف مُشار إليه (`logo`، `font.files`) موجود داخل `NOOR_IDENTITY_DIR` وبلا روابط رمزية خارجة؛ وتباين الألوان يُحسب عند البناء (R9).
5. **snapshot-manifest**: يُعاد حساب `tree_sha256` من الشجرة داخل المستودع ويُقارن؛ الأدوات الثلاث في `scans` إلزامية؛ `exposures_closed` يطابق صفوف جدول الدستور للمنصة.
6. **labels**: لكل `check_result.*` و`approval_state.*` إدخال مستقل؛ يُرفض أي مفتاح يجمعهما.

## معرّفات صفوف التعرض (`exposures_closed`)

`EXP-ATPAS-LICENSE` · `EXP-JR-TEMPLATE` · `EXP-JR-AUTH` · `EXP-NMIS-PASSWORDS` · `EXP-QA-ROUTES-TUS` · `EXP-PRIOR-IDENTITY` (بترتيب جدول الدستور 3.0.0).

## الاختبارات المطلوبة لكل عقد (كما في 001)

مُنتِج ناتجه يجتاز المخطط والمُتحقِّق · مستهلك يقبل عينة صحيحة ويرفض حقلًا زائدًا ومسارًا مطلقًا وإصدارًا غير معروف · نسخ المخططات حرفيًا إلى `packages/noor_contracts/noor_contracts/schemas/` مع اختبار انحراف.
