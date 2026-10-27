---
description: "Task list for 001 — الخيط الواحد على منافسة مصطنعة"
---

# Tasks: الخيط الواحد على منافسة مصطنعة (Single Thread Demo)

**Input**: `specs/001-single-thread-demo/` — spec.md · plan.md · research.md · data-model.md · contracts/ · quickstart.md

**Constitution**: 3.0.0 (مصدَّق 2026-10-27؛ كانت هذه المهام قد كُتبت على 1.1.0 ثم 2.0.0) · **Decisions**: `.specify/memory/decisions.md` (ومعها SYS-12..14 وتعديل R5 وتعديلات 3.0.0)

**تحديث 2026-10-27 (002)**: لم تُحذف أي مهمة ولم يُعدَّل نص مهمة قائمة. المهام التي تمسها المواصفة 002 مُحالة في قسم «الإحالة إلى المواصفة 002 والتعارضات» قبل «Dependencies»، والتعارض مُعلَّم هناك ليُحسم بقرار لا صامتًا.

**البوابة (المبدأ XI)**: وافق م. عبدالله الحربي وم. يوسف سليم على نطاق الخطة في 2026-10-24 (بنقل م. يوسف في المحادثة). هذه الموافقة لا تثبت إغلاق أي تعرض ولا تأذن بنقل كود؛ كل نقل مشروط ببوابته أدناه. **باقٍ مفتوح**: المشغّل البشري لحساب «معتمِد المراجعة» والإذن المكتوب ومدة الاحتفاظ باسمه (الموعد 2026-11-04)؛ لا يمنع المهام، ويمنع تفعيل الحساب (T073).

**Tests**: مطلوبة. الدستور يفرض حدًا أدنى (التفويض، فصل المنافسات، العقود، الاستخراج، التصدير، فشل القراءة)، والمواصفة تفرض اختبارات SC-004 وSC-005 وFR-004. تُكتب الاختبارات أولًا وتفشل قبل التنفيذ.

**Organization**: مرتبة حسب القصص: US1 (P1) ثم US4 (P1) ثم US2 (P2) ثم US3 (P3). US4 بعد US1 لأن بيان النضج يعرض حالة الوصلات.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: يمكن تنفيذها بالتوازي (ملفات مختلفة، بلا اعتماد على مهمة غير منجزة).
- **[Story]**: US1..US4 من spec.md.
- المالك بين قوسين في الوصف عند الحاجة: (م. يوسف) · (فريق الهندسة)؛ و(م. عبدالله) للرفع من حساب قائد الفريق فقط (T104). ما لا مالك له يتبع مالك المنصة في جدول الحدود (الدستور).
- **مهام البوابات** يسجّل نتيجتها المالك في «سجل البوابات والإسقاط» آخر هذا الملف، **بلا تفاصيل تعرض حساسة**؛ الدليل الكامل خارج المستودع (`INVENTORY.2026-10-27.md` مرجعًا مجمَّدًا، و`INVENTORY.md` سجلًا حيًا).

## Path Conventions

حسب plan.md: `packages/noor_contracts/` · `platforms/{radar,nmis,atpas,jouready}/` · `samples/synthetic/tender-001/` · `tests/e2e/` · `launcher/`. الكود القديم في الجذر (`app/` `atpas_engine/` `radar/` `frontend/`) **لا يُستعمل ولا يُعدَّل** (SYS-11).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: الهيكل والأدوات المشتركة.

- [x] T001 Create the plan's directory skeleton with `.gitkeep` files: `packages/noor_contracts/noor_contracts/schemas/`, `packages/noor_contracts/tests/`, `platforms/radar/`, `platforms/nmis/`, `platforms/atpas/`, `platforms/jouready/`, `samples/synthetic/tender-001/activities/`, `tests/e2e/`, `launcher/`
- [x] T002 [P] Add ignore rules to `.gitignore` for runtime data that must never sit in the repo: `noor_data/`, `noor_exchange/`, `.jr_state/`, `**/logs/usage.jsonl`, `platforms/**/output/` — without ignoring `samples/synthetic/**/*.docx`
- [x] T003 [P] Create `packages/noor_contracts/pyproject.toml` (Python >=3.11، اعتمادية واحدة `jsonschema`، بلا مكتبة شبكة)
- [ ] T004 Decide lint for new code (م. يوسف): `ruff` (مجاني) أو `python -m compileall` حدًا أدنى (R11)؛ سجّل القرار في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md` واضبطه في `packages/noor_contracts/pyproject.toml`
- [x] T005 [P] Write the public-repo scanner `tools/scan_public_repo.py`: أنماط أسرار، مسارات مطلقة (`^[A-Za-z]:[\\/]`, `^\\\\`, `file://`, `/home|Users|mnt|var|tmp/`)، `session`/`sid=`/`token`، وقائمة أسماء حقيقية محظورة **تُقرأ من ملف خارج المستودع** يحدده متغير بيئة (لا تُكتب الأسماء في المستودع)؛ يعمل على الفرق وعلى التاريخ (SC-006) <!-- scan:allow=path.file_uri -->
- [ ] T006 Add CI workflow `.github/workflows/noor-v2.yml` يعمل على `master` و`noor-v2` وفروع الميزات: pytest لـ `packages/` و`platforms/` و`tests/e2e/`، و`node --test` للرادار، و`tools/scan_public_repo.py` (الدستور: CI على الفرع المستهدف فعليًا). لا يُعدَّل `ci-cd.yml` القديم هنا (SYS-06 مواصفة مستقلة). **(2026-10-25: كُتب `noor-v2.yml`؛ خطوة `ruff` فيه مؤقتة حتى حسم T004، فلا تُعلَّم المهمة مكتملة قبل قرار م. يوسف — نقد Codex)**

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: البوابات الأولى، وحزمة العقود، ولقطة NMIS، وأساس `noor_registry`.

**⚠️ CRITICAL**: لا تبدأ أي قصة قبل اكتمال هذه المرحلة.

### البوابات المبكرة

- [ ] T007 R2 checkpoint **2026-10-28** (م. يوسف): دليل إغلاق تعرض كلمات مرور NMIS (إزالة القيم من اللقطة + فشل الإقلاع بلا متغيرات + تدوير على النسخة الحية) وN5؛ القرار: لقطة NMIS أو «البيت الأدنى» مسارًا أساسيًا. سجّل النتيجة في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`
- [ ] T008 [P] RAD-01/02 gate **2026-10-30** (م. يوسف): فحص لقطة الرادار وتاريخ مصدرها من الأسرار **والبيانات المحمية**، مع حفظ مرجع المصدر خارج المستودع، قبل أي نقل؛ النتيجة في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`

### حزمة العقود (FR-004، المبدأ VI)

- [x] T009 [P] Copy the six approved schemas unchanged from `specs/001-single-thread-demo/contracts/*.schema.json` to `packages/noor_contracts/noor_contracts/schemas/` and add drift test `packages/noor_contracts/tests/test_schema_drift.py` (تطابق البايتات مع نسخة المواصفة)
- [x] T010 [P] Write failing schema tests `packages/noor_contracts/tests/test_schemas.py`: لكل عقد من الستة عينة صحيحة تُقبل، ورفض: حقل زائد، و`synthetic: false`، وقيمة `schema` غير معروفة (مثل `noor.tender/v2`)
- [x] T011 [P] Write failing guard tests `packages/noor_contracts/tests/test_validate_rules.py`: رفض مسار مطلق في أي حقل نصي، و`session`/`sid=`/`token`، وملف >1 ميغابايت، وترميز غير UTF-8؛ وقواعد 4–5 من `contracts/README.md`: حكم `match` بلا اقتباس أو باقتباس >300 حرف أو غير موجود حرفيًا في الملف ذي البصمة ⇐ رفض؛ ختم بدور مكرر أو ناقص (`rfp`,`proposal`,`report`) ⇐ رفض
- [x] T012 Implement `packages/noor_contracts/noor_contracts/validate.py`: `validate(doc, schema_name, quote_resolver=None)` يطبّق المخطط ثم القواعد 1–5؛ `quote_resolver(sha256) -> text|None` يُمرَّر من المستهلك، و`None` ⇐ الحكم غير مقبول (لا يُقبل `match` إذا تعذّر التحقق)

### لقطة NMIS (NMIS-N0..N10، R2)

- [ ] T013 (م. يوسف) Prepare the sanitized NMIS snapshot **outside the repo** from a source reference documented by the owner outside the repo (مرجع مصدر موثّق لدى المالك خارج المستودع): ما في N2 فقط (التطبيق، الحسابات، قوالب المهام، الكانبان، وضع العرض، المظهر، الاختبارات)؛ استبعاد قائمة N3 كاملة؛ إزالة كلمات المرور الافتراضية (N0)؛ استبدال خزنة الأسرار بوحدة تقرأ من البيئة فقط وتسرد القيم المطلوبة بلا نص مشفّر (N5)؛ الهوية من `company_profile.json` بهوية «النور» وإزالة افتراضات العميل السابق وشعاره (N4)؛ الاستماع `127.0.0.1` (N6)؛ Telegram معطّل (N7)؛ قاعدة فارغة + توليد من الكتالوج الخيالي بعد فحص الأسماء (N8)؛ بلا تاريخ (N1). شغّل `tools/scan_public_repo.py` على اللقطة قبل T014
- [ ] T014 Import the snapshot into `platforms/nmis/` only after T007 = PASS، مع `platforms/nmis/SOURCE.md` منقّح يذكر تاريخ النقل والمضمّن والمستبعد وحكم الفحص ومعرّف دليل معتمًا؛ لا يذكر اسم مستودع خاصًا أو معرّف التزام مصدر أو مسارًا محليًا. إن كان T007 = «البيت الأدنى»: لا لقطة، وتُبنى الواجهة الصغيرة على `noor_registry` وحدها
- [ ] T015 First baseline run of the imported NMIS tests **بأمر م. يوسف** (N10): سجّل الأمر والبيئة والالتزام والنتيجة والقيود في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`؛ لا يُكتب العدد في أي مكان آخر (المبدأ X)
- [ ] T016 Visual identity check after removing all defaults (شرط N4): لقطة شاشة لكل صفحة معروضة بلا أي أثر للعميل السابق؛ النتيجة في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`

### أساس `noor_registry` (يعمل في المسارين: اللقطة أو البيت الأدنى)

- [x] T017 [P] Write failing config tests `platforms/nmis/tests/test_config.py` (Q0): الإقلاع يفشل برسالة واضحة عند غياب أي من `NOOR_DATA_DIR` و`NOOR_EXCHANGE_DIR` و`NOOR_SECRET_KEY` وكلمات مرور الحسابات الأربعة؛ ويفشل إذا كان `NOOR_DATA_DIR` أو `NOOR_EXCHANGE_DIR` داخل شجرة المستودع
- [x] T018 Implement `platforms/nmis/noor_registry/config.py` لاجتياز T017 (لا قيم افتراضية لأي سر، المبدأ III)
- [x] T019 Implement SQLite schema `platforms/nmis/noor_registry/db.py` في `NOOR_DATA_DIR` (قاعدة جديدة فقط، لا ترحيل على قاعدة حية) لكل كيانات data-model.md، بقيودها حرفيًا: `tender_id` «`NT-YYYY-NNNN` يصدره NMIS وحده، فريد، لا يتغير»؛ قيد فريد (`source_name`, `source_ref`)؛ `status` ∈ {`candidate`,`accepted`,`rejected`}؛ Membership «فريد: `user_id` + `tender_id` + `role`» و`role` ∈ {`approver`,`review_approver`,`member`,`viewer`}؛ User `kind` ∈ {`proposal_manager`,`review_approver`,`member`,`viewer`} و`shared` = `false` دائمًا؛ Approval `subject_type` ∈ {`tender`,`report`,`finding`,`gap_task`,`manual_entry`,`field_completion`,`import`,`permission_grant`} و`decision` ∈ {`approved`,`approved_with_reservation`,`rejected`} و«`reservations` إلزامي مع تحفظ» و«غير قابل للتعديل» (مشغّلات تمنع UPDATE/DELETE)؛ GapProposal `state` ∈ {`pending`,`finding_approved`,`task_created`,`rejected`}؛ TenderRecord `activity_codes` «يلزم عنصر واحد على الأقل قبل إصدار `noor.tender/v1`»؛ User `enabled` «`false` لـ `review_approver` عند الإنشاء»؛ جدول CreationGrant «`capability` = `create_synthetic_tender`، لا يُستنتج من `kind`»؛ CHECK `synthetic = 1` لكل كيان
- [x] T020 [P] Write failing authz tests `platforms/nmis/tests/test_authz.py`: الهوية والفاعل من الجلسة لا من الطلب؛ `viewer` يُرفض دائمًا؛ `report`/`finding` تتطلب `review_approver` على المنافسة نفسها؛ `tender`/`gap_task` تتطلب `approver`؛ لا منح ذاتي؛ كل قرار يكتب Approval واحدًا؛ اختبر رفض استعمال صلاحية ممنوحة على منافسة أخرى وفصل سجلات المنافسات؛ الإنشاء (`import`/`manual_entry`) يُرفض بلا CreationGrant مسجّل ولو كان `kind` = `proposal_manager`، وينجح معه فيُنشئ المنافسة وصف `approver` للمنشئ وApproval `permission_grant` في معاملة واحدة، ولا يغيّر الحالة إلى «مقبولة»؛ وتحديث سجل قائم يُرفض بلا صلاحية على منافسته (FR-002a)
- [x] T021 Implement the single authorization function `platforms/nmis/noor_registry/authz.py` (`authorize(user, tender_id, action)` + `authorize_creation(user)` بتخويل CreationGrant + `record_approval(...)`) لاجتياز T020 (المبدأ I، ضابط الأمان 1)
- [x] T022 Write route-enumeration test harness `platforms/nmis/tests/test_routes_authz.py`: يمر على `app.url_map` الفعلي (لا قائمة يدوية)، ويثبت لكل مسار POST وكل تنزيل: يُرفض بلا جلسة، ويُرفض لحساب `viewer`، ويُرفض بلا رمز CSRF؛ افحص جميع الطرق التي تغيّر الحالة، بما فيها الاستئناف والاستيراد، وارفض أي تغيير عبر GET؛ وأعد تشغيل الحزام بعد إضافة المسارات (FR-022، SC-005، ضابطا الأمان 1–2)
- [x] T023 Implement session + CSRF in `platforms/nmis/noor_registry/security.py`: مفتاح جلسة مستقل من `NOOR_SECRET_KEY` (NMIS-R)، وCSRF على كل طلب يغيّر حالة أو ينزّل، بما فيه JSON والاستيراد
- [x] T024 [P] Write failing store tests `platforms/nmis/tests/test_artifacts.py`: فتح بمعرّف داخلي فقط، رفض `..` والمسارات المطلقة والروابط الرمزية الخارجة من الجذر، أسماء بالبصمة، حد حجم (JR-R، ضابط الأمان 3)
- [x] T025 Implement content-addressed store `platforms/nmis/noor_registry/artifacts.py` داخل `NOOR_DATA_DIR` لاجتياز T024
- [x] T026 [P] Write failing runner tests `platforms/nmis/tests/test_runners.py` بأداة وهمية: قائمة وسائط، مهلة، بلا `shell=True`، بيئة صريحة، الفشل يُرجع خطأً ظاهرًا لا نتيجة ناقصة
- [x] T027 Implement `platforms/nmis/noor_registry/runners.py` لاجتياز T026 (ضابط الأمان 6)
- [ ] T028 Implement network-block harness `tests/support/no_network/` (Python: `sitecustomize.py` يُحقن عبر `PYTHONPATH` في كل عملية تابعة؛ Node: ملف preload عبر `NODE_OPTIONS=--require`) يرفض أي اتصال غير loopback، مع اختبار ذاتي `tests/support/test_no_network.py` يثبت الرفض في عملية NMIS وفي عمليات تابعة (ضابط الأمان 7، R11). **(2026-10-25: الحارس واختباره الذاتي مكتوبان ومجتازان، ومنها حفيد العملية؛ لا تُعلَّم مكتملة حتى يُثبت توريثه لكل أداة تابعة فعلية — الرادار وATPAS وJoUReady — في T093، بشرط Codex)**
- [x] T029 Implement synthetic account seeding `platforms/nmis/noor_registry/seed.py`: أربعة حسابات (`proposal_manager`، `review_approver`، `member`، `viewer`) بكلمات مرور من البيئة؛ تنسخ القاعدة قبل البذر (NMIS-R)؛ `proposal_manager` بلا CreationGrant حتى T030؛ `review_approver` بلا Membership و`operator_label` فارغ حتى T073؛ يُنشأ الحساب معطّلًا، ويرفض تسجيل دخوله حتى اكتمال T073
- [x] T030 Implement local grant procedure `platforms/nmis/noor_registry/grant.py` (CLI محلي) باختبار يستخدم أسماء وهمية فقط: يتحقق من هوية م. يوسف عبر حساب تهيئة مغاير للحساب الممنوح، ومن الإذن الموثّق، ولا يقبل هوية المنفّذ من وسيط الطلب ولا يسمح بالمنح للنفس أو لحساب `viewer`؛ ويسجّل قرار `permission_grant` عبر دالة التفويض الموحدة. مسار تخويل إنشاء المنافسات المصطنعة يسجّل CreationGrant لحساب «مدير العروض» بإذن م. يوسف قبل Q1، دون اشتراط اسم مشغّل «معتمِد المراجعة» أو مدة الاحتفاظ به. ومسار منح `review_approver` يبقى معطّلًا حتى تسجيل إذن م. يوسف بصفته المالك والمشغّل البشري ومدة الاحتفاظ وMembership والمنح.
- [x] T031 Implement base RTL layout `platforms/nmis/noor_registry/templates/base.html` + `platforms/nmis/noor_registry/static/`: Tajawal مضمَّن محليًا مع ترخيصه (لا تحميل من الشبكة وقت التشغيل)، تمييز «مقترح / معتمد / تعذّر التحقق» بالنص والشكل لا باللون وحده، تنقّل بلوحة المفاتيح، تسميات لقارئات الشاشة (المبدأ IX)
- [x] T032 Implement launcher `launcher/noor-demo.ps1`: يرفض البدء عند غياب أي متغير مطلوب، ويشغّل NMIS على `127.0.0.1:5310` فقط مع حارس الشبكة (R9)

**Checkpoint**: العقود والتفويض والمخزن والمشغّل جاهزة؛ تبدأ القصص.

---

## Phase 3: User Story 1 — منافسة تصل إلى البيت بلا إعادة إدخال (Priority: P1) 🎯 MVP

**Goal**: منافسة مصطنعة من الرادار تظهر «مرشَّحة» في NMIS برقم `NT-…`، ويعتمدها مصرَّح له فتُنشأ مهامها.

**Independent Test**: تصدير من الرادار ⇐ استيراد ⇐ اعتماد ⇐ ظهور المهام، بلا إدخال يدوي لبيانات المنافسة (Q1–Q4).

### Tests for User Story 1 ⚠️ (تُكتب أولًا وتفشل)

- [ ] T033 [P] [US1] Producer test `platforms/radar/test/noor-candidate-export.test.mjs` (`node --test`): الناتج يحمل `schema: noor.tender-candidate/v1` والحقول الإلزامية و`synthetic: true`، وبلا أي مسار أو معرّف جلسة
- [ ] T034 [P] [US1] Cross-contract test `packages/noor_contracts/tests/test_w1_candidate.py`: ناتج التصدير على العينة يجتاز `validate(..., "tender-candidate")`
- [x] T035 [P] [US1] Consumer import tests `platforms/nmis/tests/test_import_candidate.py`: عقد صحيح ⇐ «مرشَّحة» بمعرّف `NT-YYYY-NNNN`؛ الوارد نفسه مرتين (المصدر ومرجعه نفساهما، ولو بلا رقم اعتماد) ⇐ المعرّف نفسه، وتحديث `title`/`closing_at`/`source_updated_at` فقط مع ChangeLog؛ عقد بمسار أو حقل زائد ⇐ رفض؛ الاستيراد بحساب `viewer` أو `member`، أو بـ«مدير العروض» قبل CreationGrant ⇐ رفض **قبل فتح ملف التبادل** ويُسجَّل `import` عند القبول؛ المنشئ يحصل على `approver` مع `permission_grant`، والمنافسة تبقى «مرشَّحة»؛ التكرار يتطلب صلاحية على المنافسة القائمة (Q1a، Q1، Q2، SC-005، FR-002a) اختبر إعادة الاستيراد بحساب آخر لديه CreationGrant بلا صلاحية على المنافسة القائمة ⇐ رفض بلا تغيير؛ وإنشاء منافسة مصطنعة ثانية ⇐ معرّف مستقل ومنحة `approver` للمنشئ على الثانية فقط.
- [x] T036 [P] [US1] Approval tests `platforms/nmis/tests/test_tender_approval.py`: `approver` يقبل ⇐ «مقبولة» + مهام القالب بمسؤول وموعد + Approval؛ `viewer`/`member` ⇐ رفض بلا تغيير حالة ولا مهام؛ `closing_at` ناقص ⇐ يمنع الاعتماد حتى `field_completion` مسجّل (Q3، Q4، الحالة الحدية الأولى)
- [ ] T037 [P] [US1] Manual entry tests `platforms/nmis/tests/test_manual_entry.py`: الإدخال بلا مرجع مصدر يعرض التطابقات المحتملة (الجهة نفسها + تشابه العنوان بعد التطبيع العربي + `closing_at` ±7 أيام)، ويشترط قرارًا (اختيار قائم أو إنشاء جديد) يُسجَّل `manual_entry` (FR-001، R3). لا يُقبل تأكيد إنشاء سجل رغم التطابقات، ولا اختيار سجل قائم، إلا بعد فحص عُرض للمستخدم؛ يُربط قرار التأكيد أو الاختيار بالحقول وقائمة المعرّفات المعروضة في جلسة المستخدم، وتُرفض المحاولة المباشرة أو القائمة المتغيرة، ويُسجَّل القرار المرتبط بها (نقد Codex 2026-10-25). اختيار سجل قائم أو تعديل حقوله يُرفض بلا صلاحية على منافسته، ولا يصدر معرّفًا جديدًا أو يمنح `approver` جديدًا؛ اختبر ذلك بحساب مخوّل بالإنشاء لكنه بلا عضوية في السجل القائم.

### Implementation for User Story 1

- [ ] T038 [P] [US1] (فريق الهندسة) Write `samples/synthetic/tender-001/tender-candidate.json` ونسختين: تكرار بحقل متغير، وأخرى تحمل `closing_at: null`؛ مع مدخلها في `samples/synthetic/tender-001/RIGHTS.md` (من كتب، ومتى، واستقلالها عن أي منافسة)؛ فحص أسماء قبل الضم (NMIS-N8)
- [ ] T039 [US1] (م. يوسف) Import the sanitized radar snapshot into `platforms/radar/` after T008 = PASS، مع `platforms/radar/SOURCE.md` (بقاعدة T014: منقّح، بلا اسم مستودع خاص أو معرّف التزام مصدر أو مسار محلي)؛ قاعدة نسخة متسقة (`VACUUM INTO`) خارج المستودع بمسار صريح في الإعداد، والتشغيل الحي معطّل افتراضيًا، ولا ترحيل مخطط تلقائي على النسخة (RAD-04، RAD-06، المبدأ IV)
- [ ] T040 [US1] Implement synthetic seed `platforms/radar/scripts/noor-seed-synthetic.mjs`: يضيف منافسة العينة (T038) إلى قاعدة النسخة فقط، ويرفض العمل على قاعدة التشغيل
- [ ] T041 [US1] Implement export `platforms/radar/scripts/lib/noor-candidate-export.mjs`: يقرأ قاعدة النسخة ويكتب `noor.tender-candidate/v1` إلى `NOOR_EXCHANGE_DIR` بحقول محددة (`source_name`, `source_ref`, `source_updated_at`, …) بلا مسارات (RAD-05)، لاجتياز T033–T034
- [x] T042 [US1] Implement `platforms/nmis/noor_registry/registry.py`: إصدار المعرّف وصف `approver` للمنشئ وApproval `permission_grant` داخل معاملة واحدة مع القيد الفريد (FR-002a)، والتحديث عند التكرار مع ChangeLog، والتطبيع العربي (التشكيل، الألف/الياء/التاء المربوطة، المسافات)، والتطابقات المحتملة (R3)
- [ ] T043 [US1] Implement import route in `platforms/nmis/noor_registry/views_import.py`: يتحقق أولًا من الهوية و`authorize_creation` (FR-002a) **قبل فتح ملف التبادل**؛ يختار المستخدم ملفًا من `NOOR_EXCHANGE_DIR` باسمه (بيانات لا مسار)؛ قبل فتح ملف التبادل، ارفض `..` والمسار المطلق والرابط الرمزي الخارج من `NOOR_EXCHANGE_DIR`، واقصر الاختيار على ملف داخله؛ تحقق بالمخطط وبجميع قواعد `validate.py` وحد الحجم قبل استعمال أي حقل، ثم الإنشاء أو التحديث (التحديث بـ`authorize(..., "import")` على المنافسة القائمة) (ضابط الأمان 4)، لاجتياز T035. تُفتح نسخة الملف المختار بطريقة تمنع اتباع رابط يُستبدل بعد الفحص، ويُتحقق من الملف المفتوح وحجمه قبل القراءة؛ يُختبر تبديل الملف بين الاختيار والفتح (نقد Codex 2026-10-25)
- [x] T044 [US1] Implement tender list and page in `platforms/nmis/noor_registry/views_tenders.py` + `platforms/nmis/noor_registry/templates/tenders/`: الحالات، وعمر البيانات ومصدرها (RAD-07)، وتنبيه الحقول الناقصة، وأقسام فارغة للمهام والإصدارات والتقارير والثغرات وسجل القرارات (FR-005)
- [x] T045 [US1] Implement accept/reject + single task template `platforms/nmis/noor_registry/task_template.json` (لكل مهمة دور مسؤول وإزاحة موعد) و`platforms/nmis/noor_registry/views_approval.py` (FR-006، FR-007)، لاجتياز T036. إذا أُسندت المهمة احتياطيًا إلى المعتمِد لغياب عضو مخوّل، يُسجَّل دوره الفعلي `approver` ويظهر أن الإسناد احتياطي؛ ويختبر T036 تطابق دور المسؤول المسجّل مع صلاحياته (نقد Codex 2026-10-25)
- [ ] T046 [US1] Implement manual entry in `platforms/nmis/noor_registry/views_manual.py` + field completion in `platforms/nmis/noor_registry/views_approval.py` (بديل W1)؛ الإنشاء يمر بـ`authorize_creation` ومنح `approver` للمنشئ كما في T042 (FR-002a)، لاجتياز T037 أما اختيار سجل قائم وأي تعديل عليه فيمران بتفويض على منافسته قبل تسجيل قرار `manual_entry` أو تغيير أي حقل، دون منحة `approver` تلقائية. والتأكيد رغم التطابقات والاختيار مربوطان بالفحص المعروض كما في T037 (نقد Codex 2026-10-25). عند اختيار سجل قائم، يُعاد حساب التطابقات من الحقول المرتبطة بالفحص المعروض؛ إذا تغيّرت القائمة أو لم يعد السجل المختار ضمنها، يُرفض القرار بـ`409` دون تسجيله. يختبر T037 هذا المسار.
- [ ] T047 [US1] W1 drop decision **2026-11-01** (م. يوسف): شغّل Q1–Q2؛ «اجتاز» أو «أُسقط ⇐ إدخال يدوي L0 مُفصَح»؛ سجّل في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md` و`platforms/nmis/noor_registry/maturity.json` (SC-008)
- [ ] T048 [US1] W2 drop decision **2026-11-02** (م. يوسف): Q3–Q4 + منع التكرار؛ إن فشل ⇐ البيت الأدنى بتفويض مُختبر؛ وإن تعذّر ⇐ لا يُوصف العرض «خيطًا عاملًا متصلًا» ويُحسم النطاق مع م. يوسف؛ السجل كما في T047

**Checkpoint**: القصة 1 تعمل وحدها عرضًا مستقلًا.

---

## Phase 4: User Story 4 — إفصاح صادق أمام اللجنة (Priority: P1)

**Goal**: حساب العرض يرى النضج L0–L3 لكل منصة ووصلة، و«ما لم يُنفَّذ»، ولا يستطيع أي تعديل.

**Independent Test**: فتح البيت بحساب العرض، والتحقق من البيان والإفصاح ورفض كل تعديل (Q11، Q12).

### Tests for User Story 4 ⚠️

- [ ] T049 [P] [US4] Disclosure tests `platforms/nmis/tests/test_disclosure.py`: بيان نضج للمنصات الخمس وW1–W5؛ قائمة «ما لم يُنفَّذ» تذكر حرفيًا: XER ومونت كارلو مؤجلان، والتحليل السريع خارج الخيط العامل، وحكم النموذج المحلي غير مفعّل، وفحص إحالات SBC المحدود لا يحقق المطابقة الهندسية الكاملة، والتطور من ثلاث وحدات إلى خمس مع استبدال وحدة التدقيق بـJoUReady وحالة تأكيد المرشدين (FR-020)؛ الوصلة `dropped_manual` تُعرض خطوة يدوية مُفصَحًا عنها (Q12)
- [ ] T050 [P] [US4] Viewer read-only tests `platforms/nmis/tests/test_viewer_readonly.py` فوق حزام T022: كل مسار تعديل وكل تنزيل غير مسموح مرفوض لـ `viewer` (FR-022، Q11، NMIS-R). تحقق أيضًا من غياب الأكاديمية ولوحة الإدارة ورابط التحليل السريع العامل وأي فعل تشغيل حي من واجهات NMIS المعروضة (FR-023)
- [ ] T051 [P] [US4] Numbers tests `platforms/nmis/tests/test_numbers.py`: أي رقم معروض بلا تعريف وعينة وتاريخ وطريقة يُعرض «غير مُقاس» (FR-021)

### Implementation for User Story 4

- [ ] T052 [US4] Implement maturity config `platforms/nmis/noor_registry/maturity.json` + loader `platforms/nmis/noor_registry/maturity.py` (MaturityEntry: `component`، `level` L0–L3، `state` `working`/`dropped_manual`، `disclosure`، `decided_at`) والقائمة الثابتة لـ«ما لم يُنفَّذ»
- [ ] T053 [US4] Implement home disclosure section `platforms/nmis/noor_registry/templates/home.html` (البيت: المنافسات + بيان النضج + «ما لم يُنفَّذ»)، لاجتياز T049
- [ ] T054 [US4] Implement number display helper `platforms/nmis/noor_registry/metrics.py` (رقم مع تعريفه وعينته وتاريخه وطريقته، أو «غير مُقاس»)، لاجتياز T051

**Checkpoint**: US1 وUS4 = MVP قابل للعرض بإفصاح صادق حتى لو سقطت W3–W5.

---

## Phase 5: User Story 2 — مخرَج العرض الفني من البيت (Priority: P2)

**Goal**: من صفحة المنافسة المقبولة يُبنى Word عربي بهوية «النور» من بيانات السجل، ويظهر إصداره ببصمته بلا مسار.

**Independent Test**: بناء من منافسة مقبولة، وفتح الملف للتحقق من المشروع والجهة وRTL والهوية (Q5، Q6).

### البوابات

- [ ] T055 [US2] ATP-D0 gate **2026-11-02** (م. يوسف): دليل جدول الدستور (وقف المفاتيح المكشوفة + إبطالها وتدويرها + توثيق نطاق التعرض وخطة التاريخ + تحقق بمفتاح عام بلا سر توقيع موزَّع + لقطة منقّحة فقط)؛ النتيجة في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`
- [ ] T056 [US2] ATP-D7 content-rights decision before W3 (م. يوسف): إن لم تُحسم ملكية المكتبة الحالية ⇐ أنشطة مصطنعة يكتبها فريق الهندسة (المبدأ XIII)؛ السجل في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`

### Tests for User Story 2 ⚠️

- [ ] T057 [P] [US2] Contract tests `packages/noor_contracts/tests/test_w3_contracts.py`: مُنتِج `noor.tender/v1` (NMIS) ومستهلكه (`atpas_cli`)، ومُنتِج `noor.proposal-version/v1` ومستهلكه؛ `identity_profile` = `noor`؛ لا حقل مسار (`output_file`) في أي منهما
- [ ] T058 [P] [US2] Build tests `platforms/atpas/tests/test_atpas_cli_build.py`: Word بفقرات RTL وخط Tajawal، وهوية «النور» فقط، والمشروع والجهة مطابقان لـ `tender/v1`، والنشاط بلا محتوى مصرَّح يُرفض بسببه في `rejected_activities` ولا يدخل الملف (Q5، Q6، FR-011)
- [ ] T059 [P] [US2] NMIS build tests `platforms/nmis/tests/test_build_flow.py`: الطلب من منافسة مقبولة فقط، وProposalVersion (`version`، `sha256`، `built_at`، `requested_by`) بلا مسار ظاهر في الصفحة أو العقد، وإعادة البناء ⇐ إصدار جديد والتقارير السابقة تبقى على إصدارها، وفشل الأداة يظهر صريحًا

### Implementation for User Story 2

- [ ] T060 [US2] (فريق الهندسة) Write synthetic activities `samples/synthetic/tender-001/activities/*.docx` ونشاطًا موسومًا «غير مصرَّح» لـ Q6، ونشاطًا إنجليزيًا مصطنعًا مستقلًا يكتبه فريق الهندسة لاختبار T069، مع توثيق حقه في `RIGHTS.md`، و`project_type` في العينة، ومدخلاتها في `samples/synthetic/tender-001/RIGHTS.md`
- [ ] T061 [US2] (م. يوسف) Import the selected ATPAS engine snapshot into `platforms/atpas/` after T055 = PASS: المحرك و`utils/` اللازمة وقائمة تبعيات تشغيل صريحة (metadata، style_templates، `assets/fonts`، `version.json`، المتطلبات) بعد فحص الهوية والبيانات؛ بلا واجهة ولا أدوات مفاتيح ولا قائمة ATP-D3؛ مع `platforms/atpas/SOURCE.md` (بقاعدة T014) (ATP-D1، ATP-D2). افحص الأصول الثنائية والقوالب من بيانات العملاء أيضًا، ثم شغّل الاختبارات المنقولة أول مرة بأمر م. يوسف وسجّل خط الأساس وقيوده (ATP-D9 وATP-R)
- [ ] T062 [US2] Implement internal mode in `platforms/atpas/` (ATP-D5): إعداد صريح، متسق في بوابة البدء وفي المحرك (استدعاء الترخيص خلف واجهة صغيرة)، معزول عن بناء التوزيع، وبلا تصادم مع حالة التفعيل في `%APPDATA%` (ATP-R)
- [ ] T063 [US2] Move identity to config in `platforms/atpas/company_profile.json` (ATP-D6): «النور» فقط، وإزالة افتراضات العميل السابق من الكود وأيقونة البناء
- [ ] T064 [US2] Read content-library path from config in `platforms/atpas/` (ATP-D7) بدل المسار المثبت في مكتبة المحتوى والمنشئ، ويشير إلى نسخة منفصلة من أنشطة العينة
- [ ] T065 [US2] Drop the file-path field from every proposal-registry store in `platforms/atpas/` — JSON وCSV وفهرس SQLite (ATP-D8)
- [ ] T066 [US2] Implement `platforms/atpas/atpas_cli/build.py`: يقرأ `noor.tender/v1`، يكتب Word إلى مجلد مخرجات يمرّره NMIS، ويكتب `noor.proposal-version/v1`، لاجتياز T058
- [ ] T067 [US2] Implement in NMIS `platforms/nmis/noor_registry/views_build.py`: يطلب `project_type` من قائمة محددة ويسجّل استكماله بقرار `field_completion` قبل البناء؛ لا يفترض وروده في عقد الرادار. اختيار الأنشطة وحفظها على المنافسة (`activity_codes`، عنصر واحد على الأقل)، وكتابة `noor.tender/v1`، واستدعاء `atpas_cli` عبر `runners.py`، وحفظ الملف بالبصمة، وتسجيل ProposalVersion، لاجتياز T057 وT059
- [ ] T068 [US2] Prepare W3 fallback before **2026-11-04**: Word مبني مسبقًا من بيانات العينة نفسها، محفوظ في `NOOR_DATA_DIR`، مع نص إفصاح L0 في `platforms/nmis/noor_registry/maturity.json`
- [ ] T069 [US2] اختبار بصري موثّق لتصدير Word بعينتين مصطنعتين عربية وإنجليزية؛ افحص الاتجاه والخط والأرقام والجداول والاقتباسات، وسجّل اللقطات والنتيجة والقيود في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md` (المبدأ IX)
- [ ] T070 [US2] W3 drop decision **2026-11-04** (م. يوسف): Q5–Q6؛ السجل كما في T047

**Checkpoint**: US1 + US4 + US2 تعمل.

---

## Phase 6: User Story 3 — مراجعة بالدليل وختم ثم عودة الثغرات (Priority: P3)

**Goal**: فحوص حتمية فقط + فحص إحالات SBC المحدود + ملف ختم مستقل، والثغرات تعود مقترحات لا تصبح مهامًا إلا باعتمادين.

**Independent Test**: عرض مصطنع معروف الثغرات ⇐ مقارنة بـ `expected_findings.json` ⇐ تحقق الختم ⇐ اعتماد ثغرة إلى مهمة (Q7–Q10b).

### البوابات

- [ ] T071 [US3] JoUReady template gate **2026-11-04** (م. يوسف): لقطة منقّحة بلا تاريخ + فحص محتوى القالب وإزالة تلميح المفتاح من إعداد المزودين (جدول الدستور، JR-D1)؛ السجل في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`
- [ ] T072 [US3] Approval-routes gate **2026-11-04** (م. يوسف)، قبل T083: يفحص م. يوسف حزمة النقل المنقّحة خارج المستودع ويثبت غياب الخادم والبوابة ومشغّل الوكلاء وعدم قابليتها للتشغيل؛ ويجتاز T080 على تقرير اختباري بعد تنفيذ مسارات الاعتماد في T088، بلا اعتماد على لقطة JoUReady. يُعاد فحص الحزمة بعد النقل في T078. يُسجَّل الحكم ومرجع دليل معتم في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`
- [ ] T073 [US3] R6 operator gate **2026-11-04** (م. يوسف): يحدد م. يوسف المشغّل البشري في رد خاص محدود الوصول مع إذن مكتوب بمعرّف الحساب ومعرّف المنافسة الداخلي، ويحدد مدة الاحتفاظ بالاسم (مقترح: حتى 2026-12-16 أو انتهاء المشاركة، ثم الحذف من NMIS والمراسلات خلال 7 أيام)؛ ثم يشغّل `platforms/nmis/noor_registry/grant.py` محليًا. **الاسم لا يُكتب في المستودع ولا هنا**؛ يُسجَّل في «سجل البوابات» فقط: «حُدِّد/لم يُحدَّد» والتاريخ. لا يُفعَّل الحساب قبل ذلك

### Tests for User Story 3 ⚠️

- [ ] T074 [P] [US3] Contract tests `packages/noor_contracts/tests/test_w4_w5_contracts.py`: مُنتِج ومستهلك `noor.review-report/v1` و`noor.seal/v1` و`noor.gap-proposal/v1`، ومنها قاعدتا 4–5 (اقتباس كل مصدر في الملف ذي بصمته، وأدوار الختم `rfp` ثم `proposal` ثم `report` بلا تكرار ولا نقص)
- [ ] T075 [P] [US3] SBC tests `platforms/jouready/tests/test_sbc_refs.py`: استخراج الإحالات بالأرقام العربية والهندية بعد التطبيع مع الإصدار والجزء، والمقارنة (ناقصة/مختلفة)، و`locator` بصيغة `p<فقرة>` أو `t<جدول>:r<صف>c<عمود>`، واقتباس «مطابق» حرفي ≤300 حرف، وملف غير مقروء ⇐ `unverifiable` لا «غير موجود» (FR-013..015، Q8)
- [ ] T076 [P] [US3] Seal tests `platforms/jouready/tests/test_seal.py`: التحقق ينجح على الملفات الثلاثة غير المعدلة، ويفشل ظاهرًا عند تغيير بايت واحد في كل ملف منها مع بقاء ملف الختم كما هو (SC-004، Q9)؛ و`notice` لا يصف الختم توقيعًا أو إثبات هوية
- [ ] T077 [P] [US3] Review accuracy test `platforms/jouready/tests/test_review_expected.py`: على العينة يكتشف التقرير 100% من الثغرات المتوقعة ضمن نطاق الفحوص الحتمية، ولا يصدر `match` بلا اقتباس متحقق (SC-003، Q7)
- [ ] T078 [P] [US3] Boundary test `platforms/jouready/tests/test_boundary.py`: لا مجلد خادم ولا بوابة في `platforms/jouready/`، ولا استيراد لهما ولا تشغيل، ولا مزود سحابي مفعّل ولا المرحلة 2، ولا إحالة `OpenCode Go` في الإعداد (JR-D3/D4 وJR-D6 وJR-D9 المعدّلة، دليل الدستور 1.1.0)
- [ ] T079 [P] [US3] Path-confinement test `platforms/jouready/tests/test_paths.py`: الأداة ترفض أي ملف خارج الجذر المصرح به، وتكتب الحالة والسجلات خارج شجرة الكود (JR-R، JR-D5)
- [ ] T080 [P] [US3] NMIS review-approval tests `platforms/nmis/tests/test_review_approval.py` (Q10b): اعتماد التقرير أو حكم بحسابات `viewer` و`member` و`proposal_manager` بلا منح، وبـ`review_approver` قبل المنح ⇐ رفض والتقرير يبقى `proposed`؛ بعد المنح المسجّل ⇐ يُقبل؛ مسار الاستيراد لا يغيّر `approval_state`؛ اختبر رفض دخول حساب `review_approver` المعطّل؛ وفي قاعدة اختبار معزولة فقط، اختبر رفض مسار الاعتماد لحساب مفعّل بلا `Membership`، دون استعمال اسم المشغّل الحقيقي (SC-005)
- [ ] T081 [P] [US3] NMIS gap-flow tests `platforms/nmis/tests/test_gap_flow.py` (Q10): `pending` ⇐ `finding_approved` (من `review_approver`) ⇐ `task_created` (من `approver`) بقرارين مسجّلين وتحفظاتهما؛ المهمة تحمل `finding_key` والمعرّف وإصدار العرض؛ مراجعة ثانية بالمفتاح نفسه تربط المهمة القائمة ولا تكررها (FR-018، FR-019)

### Implementation for User Story 3

- [ ] T082 [US3] (فريق الهندسة) Write `samples/synthetic/tender-001/rfp.docx` (بإحالات SBC)، و`samples/synthetic/tender-001/expected_findings.json`، ونسخة عرض بثغرات معروفة، ومدخلاتها في `RIGHTS.md`. الكراسة التالفة لـ Q8 تُولَّد وقت الاختبار بقص نسخة، لا تُحفظ
- [ ] T083 [US3] (م. يوسف) Import the deterministic-library snapshot into `platforms/jouready/` after T071 = PASS وT072 = PASS: الفحوص الحتمية المنطبقة ومواصفاتها واختباراتها فقط، بلا خادم ولا بوابة ولا مشغّل وكلاء، والمزودون السحابيون معطّلون، و`JR_STATE_DIR` و`JR_USAGE_LOG` و`JR_DATA_DIR` خارج الشجرة؛ مع `platforms/jouready/SOURCE.md` (بقاعدة T014؛ مرجع مصدر موثّق لدى المالك خارج المستودع)، ثم أول تشغيل لاختباراتها بأمر المالك (JR-D10)
- [ ] T084 [US3] Implement `platforms/jouready/jr_cli/sbc_refs.py` (FR-013، R7)، لاجتياز T075
- [ ] T085 [US3] Implement `platforms/jouready/jr_cli/seal.py` (إنشاء + `verify-seal`، R8)، لاجتياز T076
- [ ] T086 [US3] Implement `platforms/jouready/jr_cli/review.py`: يقرأ الكراسة وإصدار Word داخل الجذر المسموح بحد حجم وعدد عناصر (ضابط الأمان 5)، ويشغّل الفحوص الحتمية + SBC، ويكتب `noor.review-report/v1` بحالة `proposed` و`noor.seal/v1` (بعد إغلاق التقرير) و`noor.gap-proposal/v1` بحالة `pending` لكل `mismatch`، لاجتياز T074 وT077–T079
- [ ] T087 [US3] Implement review flow in NMIS `platforms/nmis/noor_registry/views_review.py`: استدعاء `jr_cli` عبر `runners.py`، واستيراد التقرير والختم والثغرات مع التحقق بالمُتحقِّق و`quote_resolver` من المخزن، وربطها بـ ProposalVersion، وعرض «مقترح / معتمد / تعذّر التحقق» بوضوح، وزر «تحقق الختم» بنص «تحقق من سلامة الملفات، ليس توقيعًا ولا إثبات هوية»
- [ ] T088 [US3] Implement approval actions in `platforms/nmis/noor_registry/views_approval.py`: اعتماد التقرير/الحكم من `review_approver` فقط، وإنشاء المهمة من الثغرة من `approver` بعده، مع التحفظات، لاجتياز T080–T081
- [ ] T089 [US3] Prepare W4 fallback before **2026-11-06**: تقرير مُعد مسبقًا يقبله NMIS فقط إذا طابقت `rfp_sha256` و`proposal_sha256` الملفين المعروضين، مع إفصاح أن المراجعة لم تُشغَّل حيًا، في `platforms/nmis/noor_registry/views_review.py`
- [ ] T090 [US3] Implement W5 manual gap entry `platforms/nmis/noor_registry/views_manual.py`: مقترحات مرتبطة بالمعرّف وإصدار العرض، بالإفصاح نفسه، وتخضع للاعتمادين ومنع التكرار (بديل W5)
- [ ] T091 [US3] W4 drop decision **2026-11-06** (م. يوسف): Q7–Q9؛ السجل كما في T047
- [ ] T092 [US3] W5 drop decision **2026-11-07** (م. يوسف): Q10–Q10b؛ السجل كما في T047

**Checkpoint**: الخيط كاملًا يعمل أو بخطوات يدوية مُفصَح عنها.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T093 Write e2e test `tests/e2e/test_single_thread.py`: الخيط كاملًا على العينة مع حارس الشبكة في NMIS وكل العمليات التابعة (الرادار، ATPAS، JoUReady)، وفحص كل عقد ناتج بالمُتحقِّق (لا مسار ولا `session`)، ومؤشرات الأثر الأربعة على العينة (عدد مرات الإدخال، الزمن إلى المهام، نسبة الثغرات المكتشفة، نسبة الثغرات المحوّلة لمهام)
- [ ] T094 Run 3 consecutive timed rehearsals ≤3 دقائق بلا تدخل غير مُعلن (SC-001، Q13) وسجّل الأمر والبيئة والالتزام والنتيجة والقيود في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`
- [ ] T095 Verify SC-002 (إدخال واحد للحقول الدنيا لكل وصلة لم تسقط) من ناتج T093، وسجّله كما في T094
- [ ] T096 [P] Manual accessibility + RTL checklist (لوحة مفاتيح، تباين، قارئ شاشة، تمييز الحالات) على صفحات NMIS والتقرير، النتيجة في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md` (المبدأ IX)
- [ ] T097 [P] Vision 2030 verifications (حدّث جدول المراجع في `specs/001-single-thread-demo/plan.md`): SBC الإصدار والأجزاء **2026-11-03** (م. يوسف) · مبادئ أخلاقيات الذكاء الاصطناعي **2026-11-05** (م. يوسف) · NDMO وNCA **2026-11-05** (م. يوسف). لا يُدّعى امتثال ولا عدم انطباق قبل المصدر الرسمي المؤرَّخ
- [ ] T098 [P] Mentors question SYS-07 قبل التجميد (م. يوسف): التطور 3←5 واستبدال وحدة التدقيق وتأجيل XER ومونت كارلو؛ حدّث نص الحالة في `platforms/nmis/noor_registry/maturity.json`
- [ ] T099 Run `tools/scan_public_repo.py` على الفرق والتاريخ قبل كل commit وقبل التجميد (SC-006)، والنتيجة في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md`
- [x] T100 راجع ادعاءات `README.md` المنشور قبل أول commit أو عرض؛ ميّز وصف النسخة السابقة من نطاق المواصفة 001، ووثّق كل رقم بتعريفه وعينته وتاريخه وطريقة إعادة إنتاجه ونتيجته، أو أزله/وسمه «غير مُقاس». لا تؤجّل هذا التصحيح إلى SYS-06. (قائمة تحقق SC-007 قبل التجميد)
- [ ] T101 Finalize the real commands in `specs/001-single-thread-demo/quickstart.md` (Q0–Q13) بعد بناء الأدوات، وشغّلها كلها
- [ ] T102 `/speckit.converge` حتى **Converged** لكل معيار قبول، وتحديث علامات هذا الملف
- [ ] T103 Freeze the demo build **2026-11-09** (م. يوسف): سجّل الالتزام المجمَّد في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md` (لا commit ولا وسم ولا push إلا بطلب صريح)
- [ ] T104 Submission (م. عبدالله، من حساب قائد الفريق، بتجهيز م. يوسف واعتماده) داخل نافذة 12–20 نوفمبر وقبل آخر يوم: اختبار كل رابط وصورة وفيديو، وصورة شاشة للرفع الناجح (FR-026)؛ السجل كما في T103
- [ ] T105 Retention follow-up (م. يوسف، حسب المدة المتفق عليها في T073): حذف اسم المشغّل من قاعدة NMIS المحلية والمراسلات، وتسجيل «تم الحذف» وتاريخه فقط في «سجل البوابات» في `specs/001-single-thread-demo/tasks.md` (المبدأ XIII)

---

## الإحالة إلى المواصفة 002 والتعارضات (2026-10-27)

> المرجع: جدول «أثر الخطة على 001» في `specs/002-full-noor-suite/plan.md`، ومهام `specs/002-full-noor-suite/tasks.md` (يُشار إليها «002 Txxx»). طبقة الجلسة الموحدة في NMIS وATPAS وJoUReady تُنفَّذ هناك لا هنا. الحالة: **إحالة** = إضافة لا تغيّر المهمة · **تعارض** = نص المهمة هنا يخالف 3.0.0 أو 002، ولا يُنفَّذ الجزء المتعارض قبل حسمه من م. يوسف وتسجيله في «سجل البوابات».

| مهمة 001 | الحالة | ما في 002 | الحسم المقترح (لا يُطبَّق قبل قرار المالك) |
|---|---|---|---|
| T007، T008، T055، T071 | إحالة | 002 T044، T048، T056، T053 تحيل إلى البوابات نفسها | تُسجَّل النتيجة مرة واحدة هنا |
| T019 (منجزة) | إحالة | 002 T012 يضيف جداول الجلسة والمنصات و`demo_gate_decision` إلى `subject_type` | لا تغيير على ما أُنجز؛ الإضافة في قاعدة جديدة |
| T022، T023 (منجزتان) | إحالة | 002 T019–T020: فحص `Origin` إلزامي على كل مسار حالة (ملاحظة تجربة العزل)، ويوسَّع حزام T022 | لا يُعاد فتح المهمتين؛ الاختبار الموسَّع شرط في 002 |
| T007 | **تعارض** | R1 المعتمد: نواة البيت **و**NMIS الكامل منصة منفصلة معًا؛ ونص T007 يخيّر بين «لقطة NMIS» و«البيت الأدنى» مسارًا أساسيًا | يبقى دليل تعرض كلمات المرور كما هو، ويُستبدل شق الاختيار بقرار R1 بتسجيل المالك |
| T008، T055، T071 (المواعيد) | **تعارض** | 002 تستهدف بوابات أبكر لعرض المنصة عاملة (RAD-02 مساء 2026-10-28، ATPAS وقالب JoUReady 2026-10-30)، وهنا 2026-10-30 و2026-11-02 و2026-11-04 | تبقى مواعيد 001 آخر موعد لوصلات W1/W3/W4، ومواعيد 002 هدفًا لبوابة العرض؛ يؤكد م. يوسف ذلك أو يوحّدها |
| T013، T014 | **تعارض** | R1 وNMIS-N11: NMIS **الكامل** (الإصدار الحالي) لقطة في `platforms/nmis/full/` منصةً مستقلة (002 T045–T046)، ونواة البيت تبقى `noor_registry`؛ وهنا: المجموعة N2 إلى `platforms/nmis/` | تُنفَّذ اللقطة مرة واحدة وفق 002، وتُعلَّم T013/T014 «مُحالة إلى 002» بقرار |
| T032 (منجزة) | **تعارض** | 002 T042 مشغّل جديد `noor-suite.ps1` وأصل `noor.localhost:5310` عبر الوكيل؛ وهنا NMIS وحده على `127.0.0.1:5310` | يبقى `noor-demo.ps1` لاختبارات 001، ويُحسم أيهما يُعرض |
| T049 | **تعارض** | 001 FR-020 المعدّلة (3.0.0) حذفت «التحليل السريع خارج الخيط العامل»، ونص T049 ما زال يطلبها حرفيًا، وتضيف 002 FR-028 «أي منصة لم تجتز شروط العرض» | يُحدَّث نص الاختبار بقرار ليطابق FR-020 المعدّلة |
| T050 | **تعارض** | 001 FR-023 المعدّلة لم تعد تمنع «التحليل السريع وظيفةً عاملة»، ونص T050 يتحقق من «غياب … رابط التحليل السريع العامل» | يُحذف هذا الجزء من الاختبار بقرار؛ الباقي (الأكاديمية، لوحة الإدارة، التشغيل الحي) كما هو |
| T061 | **تعارض** | ATP-D4 المعدّل: الواجهة المكتبية L1 من البيت (002 T057 تجهّز المحرك **والواجهة**)؛ وهنا «بلا واجهة» | لقطة واحدة وفق 002 تخدم `atpas_cli` (W3) والواجهة معًا |
| T072، T078، T083 | **تعارض** | JR-D3/D4 وJR-D6 بتعديل 3.0.0: الخادم والبوابة يُنقلان بعد `EXP-JR-AUTH` (002 T054–T055، T072–T076)؛ وهنا دليل 1.1.0 «لا خادم ولا بوابة» واختبار حدّ يفشل بوجودهما | يُعاد تعريف دليل T072 واختبار T078 على 3.0.0 (مشغّل الوكلاء لا يُنقل، ولا مزود سحابي، ولا المرحلة 2)، ولقطة واحدة وفق 002 |
| T080، T088 | إحالة | 002 T075: زر بوابة JoUReady يرسل `noor:open-approval` فينتقل الغلاف إلى صفحة اعتماد البيت (002 `internal-api.md` §4)؛ لا كتابة اعتماد من المنصة (JR-D0) | مسارات الاعتماد هنا تبقى المرجع الوحيد لسجل القرار |
| T093 | إحالة | حارس الشبكة يمتد إلى عمليات 002 ومراقبة `tools/netwatch.ps1` (002 T090) | — |
| T103 | إحالة | 002 T142 يلتزم بالتجميد نفسه 2026-11-09 | — |

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)**: يبدأ فورًا.
- **Foundational (2):** يبدأ بعد Setup. ينتظر T014 قرار T007؛ ويجوز تنفيذ واختبار أعمال NMIS المستقلة عن اللقطة، ومنها T035–T037 وT042–T046. لا يُعلن اكتمال W2 أو تكامل لقطة NMIS قبل اجتياز بوابتها.
- **US1 (3):** تبدأ أعمال NMIS المستقلة بعد تأسيس العقود والتفويض. ينتظر T039 قرار T008 ولقطة الرادار؛ ويبقى قرارا W1 وW2 في موعديهما.
- **US4 (4)**: بعد المرحلة 2؛ يقرأ حالة الوصلات من `maturity.json`، فيُستكمل نصه بعد كل قرار إسقاط.
- **US2 (5)**: بعد US1 (يحتاج منافسة مقبولة). T061 ينتظر T055 (11-02). القرار W3 (11-04).
- **US3 (6)**: بعد US2 (يحتاج إصدار Word). T083 ينتظر T071 وT072 (11-04)، وT072 يتطلب تنفيذ T088 واجتياز T080 قبله دون انتظار T083. تفعيل حساب «معتمِد المراجعة» ينتظر T073 (11-04). القراران W4 (11-06) وW5 (11-07).
- **Polish (7)**: بعد القصص؛ التجميد 11-09، والرفع 12–20 نوفمبر.

### الاعتماد بين القصص

- US1 أساس الخيط. US2 وUS3 تعتمدان على ما قبلهما في السلسلة، لكن **بدائلهما اليدوية** (T068، T089، T090) تسمح بعرضها حتى لو سقطت الوصلة السابقة.
- US4 مستقلة في الاختبار، وتعكس قرارات الإسقاط.

### داخل كل قصة

تُكتب الاختبارات أولًا. في US3 يُنفَّذ T088 ويجتاز T080 قبل بوابة T072 ونقل T083؛ ثم تُستكمل الأداة والبدائل وقرار الإسقاط في موعده.

### Parallel Opportunities

- المرحلة 1: T002 وT003 وT005 معًا؛ T004 بعد T003 (الملف نفسه).
- المرحلة 2: T008 مع T007؛ T009–T011 معًا؛ اختبارات T017 وT020 وT024 وT026 معًا.
- **بين مسارات العمل**: الرادار (T039–T041) وJoUReady (T071–T086) بالتوازي مع (NMIS T013–T032 وT042–T046، ATPAS T055–T067)، لأن الملفات منفصلة والعقود هي الحد بينها. المالك لكل المسارات م. يوسف (تعديل الحوكمة 2026-10-27).
- فريق الهندسة: T038 ثم T060 ثم T082 (تشترك في `RIGHTS.md`)، بالتوازي مع مسارات المالك.

## Parallel Example: User Story 1

```text
Task: "T033 Producer test platforms/radar/test/noor-candidate-export.test.mjs"
Task: "T034 Cross-contract test packages/noor_contracts/tests/test_w1_candidate.py"
Task: "T035 Consumer import tests platforms/nmis/tests/test_import_candidate.py"
Task: "T036 Approval tests platforms/nmis/tests/test_tender_approval.py"
Task: "T037 Manual entry tests platforms/nmis/tests/test_manual_entry.py"
```

## Implementation Strategy

### MVP أولًا (US1 + US4)

1. المرحلتان 1 و2 (مع بوابتي 10-28 و10-30).
2. US1 ⇐ تحقق Q1–Q4 ⇐ قرارا W1/W2.
3. US4 ⇐ تحقق Q11–Q12.
4. **توقف وتحقق**: هذا عرض صادق قائم بذاته حتى لو سقط ما بعده.

### التسليم التدريجي

US2 (W3، 11-04) ثم US3 (W4، 11-06؛ W5، 11-07). كل وصلة تُضاف أو تُسقط في موعدها، ولا يُؤجَّل قرار صامتًا (SC-008).

## التنفيذ بأدوات خارجية (FR-027، plan.md «أدوات التطوير»)

- **MiniMax** (`minimax/minimax-m3.1-flash` عبر OpenRouter، `"reasoning": {"effort": "xhigh"}`، المفتاح من `OPENROUTER_API_KEY`): **مسموح** للكود الجديد الصغير في المهام: T005، T009–T012، T017–T028، T030، T042، T054، T066، T075–T076، T078–T079، T084–T086 (T075 بأمثلة اختبار مبتكرة صغيرة لا ملفات العينة) — **بملفات المهمة المسماة فقط**.
- **ممنوع على MiniMax**: أي لقطة منصة قبل فحصها (T013، T039، T061، T083)، ومحتوى `samples/synthetic/` الفني (T038، T060، T082)، والوصول الشامل للمستودع، والأسرار، واسم المشغّل، وأي شيء من منافسة حقيقية.
- **قبل كل إرسال**: `tools/scan_public_repo.py` على الملفات المرسلة. **بعده**: يراجع Claude الفرق ويعتمده، وينقده Codex (قراءة فقط) عند تغيير الثقة أو الحدود.
- **Codex**: ناقد للقراءة فقط على المستودع المنقّح.

### سجل الإرسال إلى MiniMax

| التاريخ | المهمة | الملفات المرسلة | نتيجة الفحص قبل الإرسال | مراجعة Claude |
|---|---|---|---|---|
| 2026-10-24 | T005 | موجز نصي فقط (لا ملفات من المستودع) | فحص يدوي للموجز: لا أسرار ولا مسارات ولا أسماء | **فشل**: استهلك حد التوكنز بلا ملفات (~0.16$)؛ كتب Claude الفاحص واختباراته بنفسه |
| 2026-10-24 | T010–T012 | موجز + المخططات الستة المعتمدة (`contracts/*.schema.json`) | فحص نمطي للموجز (أسرار/مسارات): نظيف | قُبل بتعديلين: قاعدة `session` نصية جزئية (كانت تفوّت `session_id`)، وإصلاح عينة الختم في الاختبار |
| 2026-10-24 | T017–T018، T024–T027 | موجز نصي (تصميم `noor_registry`) | فحص يدوي: نظيف | قُبل بتعديلين: رسائل أخطاء `runners` بلا مسارات محلية، وحارس الشبكة يُفرض على العملية التابعة |
| 2026-10-24 | T019–T021 | موجز نصي (المخطط وقواعد التفويض من data-model.md) | فحص يدوي: نظيف | قُبل بثلاثة تعديلات: منع حساب `viewer` من التهيئة، وحذف الملف نصف المنشأ عند فشل الإنشاء، وإزالة استيراد احتياطي |
| 2026-10-24 | T028 | موجز نصي | فحص يدوي: نظيف | قُبل بإصلاحين: مسار `NODE_OPTIONS` بشرطات أمامية (ويندوز)، وتأكيد رمز الخطأ في الاختبار |
| 2026-10-24 | T022–T023 | موجز نصي | فحص يدوي: نظيف | قُبل بإصلاحات: `current_user` كائن لا دالة، و`display_name` في `User`، وبناء الروابط في الحزام، وبصمة الصفوف بالقيم، وفحص المجهول برمز CSRF صالح؛ وأعاد Claude كتابة `app_fixtures.py` (تخمين المخطط) |
| 2026-10-24 | T030 | موجز نصي | فحص يدوي: نظيف | **رُفض**: تخمين الواجهات، وإعادة المحاولة بعد `AuthzError`، وفحص كلمة مرور لا يعمل؛ أعاد Claude كتابة `grant.py` و`test_grant.py` |
| 2026-10-25 | T042 | موجز نصي (واجهة `registry.py` ومقتطف المخطط؛ بلا محتوى منافسات) | `tools/scan_public_repo.py --paths` على الموجز: نظيف (الأسماء لم تُفحص) | قُبل بثلاثة تعديلات: البحث بـ`=` ورفض المصدر الفارغ (كان `IS ?` فيطابق الإدخال اليدوي)، و«duplicate» لخطأ UNIQUE فقط، وجملة UPDATE ثابتة لكل حقل (~0.004$) |

> النموذج: `minimax/minimax-m3.1-flash` عبر OpenRouter بجهد `xhigh`. لم يُرسل أي ملف من منافسة حقيقية ولا من لقطة منصة ولا سر. ملاحظة: `tools/scan_public_repo.py` (T005) نفسه من إنتاج MiniMax، فلم يكن متاحًا قبل الإرسالات الأولى؛ استُعيض عنه بفحص يدوي للموجزات.

## سجل البوابات والإسقاط (SC-008)

> لا تفاصيل تعرض حساسة ولا أسماء أشخاص حقيقيين هنا (المستودع عام). الدليل الكامل خارج المستودع.

| المهمة | البند | الموعد | المالك | النتيجة | التاريخ | معرّف دليل معتم فقط؛ بلا اسم أو مسار أو تفاصيل تعرض |
|---|---|---|---|---|---|---|
| T004 | أداة lint | — | م. يوسف | `ruff` مقترح م. يوسف ومضبوط في `packages/noor_contracts/pyproject.toml`؛ **بانتظار حسم م. يوسف وحده** (لم تعد موافقة م. عبدالله لازمة، تعديل الحوكمة 2026-10-27) | 2026-10-24 | — |
| T007 | R2: تعرض NMIS ومسار البيت | 2026-10-28 | م. يوسف | — | — | — |
| T008 | RAD-01/02: تاريخ الرادار | 2026-10-30 | م. يوسف | — | — | — |
| T030 | CreationGrant لـ«مدير العروض» بإذن م. يوسف (FR-002a) | قبل Q1 | م. يوسف | اكتمل كود إجراء المنح واختباراته؛ تسجيل منحة الإنشاء بإذن م. يوسف والتحقق منها في نسخة العرض شرط مستقل قبل Q1، ولم يُثبت بعد. | 2026-10-25 | — |
| T015 | خط أساس اختبارات NMIS | — | م. يوسف | — | — | — |
| T016 | فحص الهوية المرئي (N4) | — | م. يوسف | — | — | — |
| T037/T046 | ربط الإدخال اليدوي بالفحص المعروض | — | م. يوسف | 2026-10-25: طُبّق نص Codex (إعادة حساب التطابقات عند الاختيار، ورفض 409) مع اختبار؛ **لم يُعرض الإصلاح الأخير على Codex**؛ تبقيان مفتوحتين حتى تأكيده | 2026-10-25 | — |
| T043 | تبديل الملف بين الفحص والفتح | — | م. يوسف | 2026-10-25: الكود يفحص الملف المفتوح (fstat/lstat) وحجمه؛ اختبار التضخم يجتاز؛ **اختبار تبديل الرابط الرمزي متخطّى على ويندوز**؛ تبقى مفتوحة حتى تشغيله في بيئة تدعم الروابط (نقد Codex) | 2026-10-25 | — |
| T047 | W1 | 2026-11-01 | م. يوسف | — | — | — |
| T048 | W2 | 2026-11-02 | م. يوسف | — | — | — |
| T055 | ATP-D0: مفتاح الترخيص | 2026-11-02 | م. يوسف | — | — | — |
| T056 | ATP-D7: حقوق المحتوى | قبل 2026-11-04 | م. يوسف | — | — | — |
| T069 | الاختبار البصري لـ Word | قبل 2026-11-04 | م. يوسف | — | — | — |
| T070 | W3 | 2026-11-04 | م. يوسف | — | — | — |
| T071 | قالب JoUReady وتاريخه | 2026-11-04 | م. يوسف | — | — | — |
| T072 | مسارات اعتماد JoUReady | 2026-11-04 | م. يوسف | — | — | — |
| T073 | R6: المشغّل والإذن ومدة الاحتفاظ | 2026-11-04 | م. يوسف | — | — | — |
| T091 | W4 | 2026-11-06 | م. يوسف | — | — | — |
| T092 | W5 | 2026-11-07 | م. يوسف | — | — | — |
| T094 | 3 تمرينات ≤3 دقائق | قبل 2026-11-09 | م. يوسف | — | — | — |
| T096 | الإتاحة وRTL | قبل 2026-11-09 | م. يوسف | — | — | — |
| T099 | فحص الأسرار والبيانات | قبل كل commit وقبل 2026-11-09 | م. يوسف | 2026-10-25: `--diff` نظيف للأنماط التي يفحصها الفاحص (بعد إصلاحَي Codex الأخيرين: الملفات الثنائية بلا NUL مبكر، والملفات الكبيرة في التاريخ)؛ **لم تُفحص الأسماء** لغياب القائمة الخاصة. الفحص المعتمد قبل commit: `--diff --require-blocklist` | 2026-10-25 | — |
| T103 | التجميد | 2026-11-09 | م. يوسف | — | — | — |
| T104 | الرفع | 2026-11-12..20 | م. عبدالله (رفع فقط) | — | — | — |
| T105 | حذف اسم المشغّل | حسب المدة المتفق عليها | م. يوسف | — | — | — |

## Notes

- [P] = ملفات مختلفة بلا اعتماد. كل مهمة لقطة لا تبدأ قبل بوابتها، مهما كان التوازي ممكنًا.
- لا commit ولا push إلا بطلب صريح؛ وقبل أي commit: T099 وT100 (T100 قبل أول commit لهذه الميزة رغم موقعه في المرحلة 7).
- أي تغيير في المتطلبات أثناء التنفيذ: spec.md ثم plan.md ثم هذا الملف ثم الكود (المبدأ XI).
