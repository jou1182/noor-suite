# Data Model: منظومة النور الكاملة

**Plan**: [plan.md](plan.md) · كيانات 001 (TenderRecord، User، Membership، Approval، …) **باقية كما هي** في [../001-single-thread-demo/data-model.md](../001-single-thread-demo/data-model.md). هنا الكيانات الجديدة فقط. العقود في [contracts/](contracts/).

قواعد عامة (من 001): لا حقل في عقد يحمل مسارًا مطلقًا أو معرّف جلسة أو سرًا (المبدأ VI) · الأوقات ISO 8601 بالمنطقة · `synthetic: true` في نسخة الهاكاثون لكل ما يخص المنافسات والحسابات.

## SystemSession — جلسة المنظومة (البيت يملكها، R2)

| الحقل | النوع | القاعدة |
|---|---|---|
| `sid_hash` | SHA-256 سداسي | المعرّف نفسه (256 بت عشوائي) لا يُخزَّن؛ يُخزَّن تجزيئه فقط |
| `user_id` | مرجع User | إلزامي |
| `created_at` / `last_seen_at` | وقت | `last_seen_at` يُحدَّث عند أي طلب يمر بالبيت أو وكيله |
| `idle_expires_at` | وقت | `last_seen_at` + 30 دقيقة (FR-004، قابل للتعديل في الإعداد) |
| `absolute_expires_at` | وقت | `created_at` + 8 ساعات؛ لا يُمدَّد |
| `state` | `active` · `logged_out` · `expired` · `revoked` | انظر الانتقالات |
| `theme_pref` | `system` · `light` · `dark` | تفضيل الوضع (US6) |

**الانتقالات**: `active → logged_out` (خروج) · `active → expired` (خمول أو مطلق، يُقيَّم بمؤقت البيت كل ثانية وعند كل طلب) · `active → revoked` (تعطيل الحساب أو إجراء إداري). لا عودة إلى `active`؛ الدخول الجديد يصدر جلسة جديدة. أي انتقال من `active` يُبطل كل `PlatformSession` و`DesktopHandle` المشتقة وينشر حدثًا للمقابض.

## SigningKey و PlatformCredential — المفاتيح (R2)

**SigningKey**: زوج Ed25519 للبيت؛ الخاص في ملف خارج المستودع يقرؤه البيت وحده؛ العام يُوزَّع على المنصات. لا قيمة افتراضية؛ غيابه ⇒ فشل البدء.
**PlatformCredential**: `platform_id` ∈ {`nmis_full`, `radar`, `quick_analysis`, `jouready`} · مفتاح خدمة في متغير بيئة لكل منصة (لا يُخزَّن في القاعدة) · `enabled`. **يوثّق المنصة على `/internal/authz/check` فقط ولا يوقّع شيئًا.** ATPAS يُوثَّق بالمقبض المكتبي.

## PlatformSession — جلسة المنصة (R2)

`psid_hash` · `parent_sid_hash` · `platform_id` · `created_at` · `state` ∈ {`active`, `revoked`}. تنشأ باستبدال **EntryCode** لمرة واحدة (`code_hash`، `parent_sid_hash`، `platform_id`، `expires_at` = +60 ث، `used_at`)، وتُبطَل مع الجلسة الأم. ملفها `noor_psid` host-only على أصل المنصة.

## AssertionBinding — ربط التأكيد (ذاكرة البيت فقط، R2)

`nonce` ⇐ `psid_hash` و`expires_at`. يُنشأ عند توقيع كل تأكيد ويُحذف بعد `expires_at` (≤5 ثوانٍ). **لا يُكتب في القاعدة ولا السجلات ولا يغادر البيت**؛ يستعمله `authz/check` فقط.

## AccessDecisionLog — سجل التفويض (R2، تدقيق)

`at` · `platform_id` · `user_id` (أو فارغ إن رُفض) · `result` ∈ {`ok`, `no_session`, `expired`, `forbidden`, `bad_platform_key`, `bad_assertion`} · `action` (لـ `authz/check`) · `tender_id` (اختياري). لا يحفظ `noor_sid` ولا تجزيئه. يُحتفظ به 30 يومًا (مقترح، المبدأ XIII).

## DesktopLaunchTicket و DesktopHandle — ATPAS (R3)

**DesktopLaunchTicket**: `ticket_hash` · `sid_hash` · `client` = `desktop:atpas` · `launched_pid` · `issued_at` · `expires_at` (= +60 ثانية) · `used_at` (فارغ حتى الاستبدال). **لمرة واحدة**: الاستبدال ذري (`UPDATE … WHERE used_at IS NULL AND expires_at > now`) ويتطلب `pid` = `launched_pid` وعملية حية؛ استبدال ثانٍ أو بعد الانتهاء ⇒ رفض (internal-api §3).

**DesktopHandle**: `handle_hash` · `sid_hash` · `client` · `pid` · `created_at` · `state` ∈ {`active`, `locked`} · `last_check_at`. يُقفل تلقائيًا مع أي انتقال للجلسة من `active`. الأحداث المنشورة: `logout` · `expired` · `revoked`.

## PlatformEntry — سجل المنصات (البيت، FR-001، FR-028)

| الحقل | النوع | القاعدة |
|---|---|---|
| `platform_id` | معرّف ثابت | الخمسة أعلاه |
| `display_name` | من جدول التسميات | ثابت (FR-023) |
| `upstream` | `http://127.0.0.1:<port>` أو `desktop` | عنوان المنصة خلف الوكيل؛ loopback فقط، غير ذلك ⇒ فشل البدء |
| `browser_origin` | `http://<platform>.noor.localhost:5310` | أصل المنصة المستقل الذي يخدمه الوكيل (R2) |
| `run_state` | `running` · `stopped` · `unavailable_on_device` · `not_cleared_for_demo` | الأخير يُضبط من `demo_gate` |
| `maturity` | `L0` · `L1` · `L2` · `L3` | المستوى الفعلي لا المستهدف (المبدأ X) |
| `provider_mode` | `local` · `cloud` · `none` | `none` للمنصات بلا نموذج (NMIS، ATPAS) |
| `demo_gate` | `passed` · `failed` · `at_risk` · `pending` | يُضبط بقرار مسجّل في مواعيد FR-031 فقط |
| `fr010_result` | مرجع FR010Run الأخير | يُعرض في البيت |
| `exposure_closure_ref` | نص | مرجع دليل الإغلاق (جدول الدستور) |
| `snapshot_tree_sha256` | سداسي | من بيان البصمة |

**قاعدة العرض**: `run_state = running` لا يجعل المنصة «عاملة» في العرض؛ المنصة تُعرض عاملة فقط إن `demo_gate = passed`، و`passed` يتطلب: كل بنود FR-010 «اجتاز» في آخر FR010Run على اللقطة الحالية، ودليل الإغلاق، واختبار تعداد المسارات أخضر، وكتالوج أسطحها معتمدًا (R13). قبل أول تشغيل `fr010_result` فارغ ويُعرض «لم يُقَس بعد». وإلا يُعرض `not_cleared_for_demo` مع الإفصاح. تغيير `demo_gate` يكتب `Approval` بنوع `demo_gate_decision` من م. يوسف (يُضاف إلى قائمة `subject_type` في 001).

## FR010Run و FR010Item — نتيجة قائمة الوظائف (SC-002)

**FR010Run**: `run_id` · `platform_id` · `at` · `snapshot_tree_sha256` · `checklist_version` · `passed_count` / `total_count`.
**FR010Item**: `run_id` · `item_id` (من [contracts/fr010-checklists.md](contracts/fr010-checklists.md)) · `result` ∈ {`pass`, `fail`, `blocked`} · `evidence_sha256` (بصمة الصورة في مخزن البيت) · `note`.

## IdentityProfile — ملف تعريف الهوية (FR-020، عقد `noor.identity-profile/v1`)

`system_name` · `short_name` · `company_name` · `logo` (اسم ملف نسبي داخل مجلد الهوية أو فارغ ⇒ شعار نصي) · `logo_rights_ref` · `palette.light` و`palette.dark` (`primary`, `on_primary`, `surface`, `on_surface`, `muted`, `focus`, ورموز الحالات) · `font.family` · `font.files` (نسبية) · `font.rights_ref` · `font.fallback` (اسم بديل نظام). غائب أو لا يجتاز المخطط أو ملف مُشار إليه مفقود ⇒ فشل البدء في كل منصة (US4-2). **ملف شعار موجود لكنه تالف** (لا يُقرأ صورةً) ⇒ لا فشل؛ يُعرض الاسم نصًا عند العرض (حالة spec الحدّية «شعار تالف»). لا يحمل أسماء المنصات ولا المصطلحات (ثابتة).

## LabelTable — جدول التسميات (FR-023/024، ثابت في الكود، عقد `noor.labels/v1`)

لكل مفتاح (`platform.radar`، `term.tender`، `tender_status.candidate`، `check_result.match`، `approval_state.proposed`، …): `text_ar` · `aria_label_ar` · `shape` (اسم رمز) · `color_token` (اسم رمز في اللوحة، لا قيمة). قاعدة: نتيجة الفحص (`check_result.*`) وحالة الاعتماد (`approval_state.*`) مفتاحان منفصلان ولا يُدمجان في شارة واحدة.

## ProviderConfig — إعداد المزود لكل منصة (R8، عقد `noor.provider-config/v1`)

`platform_id` · `mode` ∈ {`local`, `cloud`} · `endpoint` (loopback فقط عند `local`) · `model` · `consent` (إلزامي عند `cloud`: `provider`, `data_sent`, `processing_location`, `retention`, `signer`, `signed_on`, `signature_ed25519`). **قواعد المُحمِّل**: بناء الهاكاثون يرفض `cloud` قبل قراءة `consent` · أكثر من منصة `cloud` ⇒ فشل البدء في البيت · فشل المحلي ⇒ «تعذّر التشغيل المحلي» بلا تحوّل.

## SnapshotManifest — بيان اللقطة (R4، عقد `noor.snapshot-manifest/v1`)

`platform_id` · `source_label` (وسم بديل أو اسم المصدر بقرار المالك) · `source_commit` (اختياري، بقرار المالك) · `copied_at` · `files[]` (`path` نسبي POSIX، `size`, `sha256`) · `tree_sha256` · `scans[]` (`tool`, `version`, `result` ∈ {`clean`, `findings_resolved`}, `at`) · `exposures_closed[]` (مراجع صفوف جدول الدستور) · `binary_assets_reviewed_by` (اسم المراجع البشري) · `synthetic_data_only` = `true`.
**الانتقالات**: `staged → scanned → fingerprinted → imported`. أي تعديل في مجلد التجهيز بعد `scanned` يعيدها إلى `staged`. `imported` يتطلب تطابق `tree_sha256` المعاد حسابه داخل المستودع.

## ServerAccessLog — سجل وصول سيرفر التحليل السريع (QA-U8، FR-008)

`at_start` / `at_end` · `operator` · `files_copied[]` (مسارات نسبية على السيرفر + بصمة كل ملف) · `commands_run[]` (للقراءة والنسخ فقط). **يُحفظ عند المالك خارج المستودع** (فيه مسارات خادم). يُنسخ منه إلى المستودع عدد الملفات وبصماتها فقط عبر SnapshotManifest.

## QAJob — مهمة التحليل السريع (R7، عقد `noor.qa-analysis/v1` للحالة)

`job_id` (UUID، يُتحقق من صيغته قبل أي بناء مسار) · `tender_id` (اختياري، `NT-YYYY-NNNN`) · `level` ∈ {`quick`, `standard`, `deep`} · `state` ∈ {`uploaded`, `extracting`, `analyzing`, `rendering`, `done`, `failed`} · `progress[]` (خطوات بوقت) · `report_docx_sha256` / `report_pdf_sha256` (اختياري) · `provider_mode` · `model` · `created_by`. الملفات في `NOOR_DATA_DIR/qa/` بأسماء بالبصمة. **الانتقالات** خطّية؛ أي فشل ⇒ `failed` برسالة، ولا تقرير جزئي يُعرض مكتملًا.

## QAEvalResult — نتيجة معيار R6 (FR-016)

`at` · `model` · `sample_id` · `m1_fact_recall` (نسبة) · `m2_invented_numbers` (عدد) · `m3_seconds` · `threshold_version` · `passed` (منطقي) · `reproduce_cmd`. يُعرض في البيت بتعريفه وعينته وتاريخه (FR-029).
