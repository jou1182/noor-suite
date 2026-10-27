---
description: "Task list for 002 — منظومة النور الكاملة: خمس منصات في بيت واحد"
---

# Tasks: منظومة النور الكاملة — خمس منصات في بيت واحد (Full Noor Suite)

**Input**: `specs/002-full-noor-suite/` — spec.md (المسودة 4) · plan.md (مسودة الخطة 4) · research.md (R1–R14) · data-model.md · contracts/ (9 مخططات + README + internal-api.md + fr010-checklists.md + surfaces.md) · quickstart.md

**Constitution**: 3.0.0 (مصدَّق 2026-10-27) · **Decisions**: `.specify/memory/decisions.md` (بتعديل 3.0.0)

**البوابة (المبدأ XI)**: اعتمد م. يوسف سليم القرارين 1 (R1: نواة البيت + NMIS الكامل منصة) و2 (R2: أصل مستقل لكل منصة + تأكيد Ed25519) في 2026-10-27، وأثبتت تجربة العزل جدوى R2 **على محاكاة** (Chromium عبر Playwright المحلي، بلا vinext ولا الواجهات الحقيقية). **قرر م. يوسف البنود 3–11 و10أ في 2026-10-27** (نصها في «سجل البوابات» آخر هذا الملف)، فرُفعت علامات الحجب عنها. واعتمد الترتيب في 2026-10-27 (القرار 9). حُلّت فجوة T075 في `contracts/internal-api.md` §4 (2026-10-27). **شرط قبل `/speckit.implement`**: اعتماد م. يوسف لنطاق الخطة (صف G1 في سجل البوابات). هذه الموافقة لا تثبت إغلاق أي تعرض ولا تأذن بنقل كود؛ كل نقل مشروط ببوابته.

**Tests**: مطلوبة. الدستور يفرض حدًا أدنى (التفويض، فصل المنافسات، العقود مُنتِجًا ومستهلكًا، الاستخراج، التصدير، فشل القراءة)، والمواصفة تفرض SC-001..SC-011. تُكتب الاختبارات أولًا وتفشل قبل التنفيذ.

**Organization**: حسب القصص في spec.md: US1 (P1) ثم US2 (P1) ثم US3 (P1) ثم US4 (P2) ثم US5 (P2) ثم US6 (P3). داخل US1 وUS2 تُرتَّب المنصات حسب الخطر (R13): NMIS ⇐ الرادار ⇐ JoUReady ⇐ ATPAS ⇐ التحليل السريع — **معتمد** (القرار 9، 2026-10-27) مع الإفصاح عمّا لا يجتاز في 2026-10-30؛ والبيت منصة أم بخمسة أزرار قابلة للتطوير.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: يمكن تنفيذها بالتوازي (ملفات مختلفة، بلا اعتماد على مهمة غير منجزة).
- **[Story]**: US1..US6 من spec.md.
- **⛔ محجوبة بقرار N**: رقم القرار في جدول plan.md («قرارات تصميم تحتاج موافقة المالك»). لا تُفترض إجابة؛ لا يبدأ تنفيذ المهمة ولا جزؤها المحجوب قبل القرار.
- **⛔ محجوبة بتوضيح تصميم**: فجوة في الخطة اكتُشفت عند التفكيك؛ تُحل في `plan.md` (وعند الحاجة `spec.md`) أولًا، ثم تُنفَّذ (المبدأ XI).
- المالك بين قوسين عند الحاجة: (م. يوسف) · (فريق الهندسة). ما لا مالك له يتبع مالك المنصة (م. يوسف لكل الخمس، الدستور 3.0.0).
- **مهام البوابات** يسجّل نتيجتها م. يوسف في «سجل البوابات» آخر هذا الملف بلا تفاصيل تعرض حساسة؛ الدليل الكامل خارج المستودع.
- **إحالة إلى 001**: البوابة المشتركة مع مهمة في `specs/001-single-thread-demo/tasks.md` تُسجَّل مرة واحدة هناك ويُحال إليها هنا (مثلًا «= 001 T007»)، فلا يُكرَّر الحكم.

## Path Conventions

حسب plan.md: `packages/{noor_contracts,noor_identity,noor_sso,noor_runtime}/` · `config/identity/noor/` · `platforms/nmis/noor_registry/` (نواة البيت) · `platforms/nmis/full/` (NMIS الكامل) · `platforms/{radar,quick-analysis,atpas,jouready}/` · `platforms/_snapshots/<name>.json` · `tools/{snapshot,surfaces}/` · `tools/scan_public_repo.py` · `tools/netwatch.ps1` · `samples/synthetic/{qa-rfp-001,atpas-activities,radar}/` · `tests/e2e/` · `launcher/noor-suite.ps1`. الكود القديم في الجذر (`app/` `atpas_engine/` `radar/` `frontend/` واختبارات `tests/test_*.py` القديمة) **لا يُستعمل ولا يُعدَّل** (SYS-11).

## متغيرات البيئة (تُثبَّت هنا كما يطلب quickstart.md)

لا قيمة افتراضية لأي منها؛ غياب أيٍّ منها يُفشل البدء ويُسمّى في الرسالة (المبدأ III). المسارات كلها خارج شجرة المستودع.

| المتغير | المستهلك | ملاحظة |
|---|---|---|
| `NOOR_DATA_DIR` · `NOOR_EXCHANGE_DIR` · `NOOR_SECRET_KEY` · `NOOR_PW_PROPOSAL_MANAGER` · `NOOR_PW_REVIEW_APPROVER` · `NOOR_PW_MEMBER` · `NOOR_PW_VIEWER` | البيت | قائمة من 001 (T017–T018) |
| `NOOR_IDENTITY_DIR` | كل المنصات | مجلد ملف تعريف الهوية ومخرجات `build/` (R9) |
| `NOOR_HOME_SIGNING_KEY_FILE` | البيت وحده | المفتاح الخاص Ed25519 (R2) |
| `NOOR_HOME_PUBLIC_KEY_FILE` | المنصات الأربع الويب | المفتاح العام فقط |
| `NOOR_PLATFORM_KEY_NMIS_FULL` · `NOOR_PLATFORM_KEY_RADAR` · `NOOR_PLATFORM_KEY_QUICK_ANALYSIS` · `NOOR_PLATFORM_KEY_JOUREADY` | البيت + المنصة المعنية | مفتاح خدمة على `/internal/authz/check` فقط، لا يوقّع شيئًا |
| `NOOR_STAGING_DIR` | `tools/snapshot` فقط | مجلد التجهيز (R4)؛ يُرفض داخل المستودع |
| `NOOR_PRIVATE_REPORTS_DIR` | `tools/snapshot` و`tools/scan_public_repo.py` | تقارير الفحص الكاملة لـ م. يوسف وحده؛ خارج المستودع **وخارج** `NOOR_STAGING_DIR` (يُرفض داخل أيٍّ منهما) |
| `NOOR_BLOCKLIST_FILE` | `tools/scan_public_repo.py` و`tools/surfaces` | قائمة الهويات الممنوعة (FR-025، R10) |
| `NOOR_PROVIDER_CONFIG_DIR` | المنصات بنموذج + البيت | ملفات `noor.provider-config/v1` (R8) |
| `JR_STATE_DIR` · `JR_DATA_DIR` · `JR_USAGE_LOG` · `JR_TENDERS_ROOT` | JoUReady | خارج شجرة الكود (JR-R، JR-D5) |
| `NOOR_ATPAS_DATA_DIR` · `NOOR_ATPAS_CONTENT_DIR` | ATPAS | حالة التفعيل والجلسات (لا `%APPDATA%/ATPAS/` المشترك، ATP-R) · مكتبة الأنشطة المصطنعة (ATP-D7) |
| `NOOR_RADAR_DB` | الرادار | قاعدة مصطنعة مولَّدة (RAD-01، RAD-06) |
| أسرار NMIS الكامل | NMIS الكامل | تُسمّى في T046 من وحدة N5 على اللقطة، وتُضاف إلى هذا الجدول يوم الدخول |

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: الهيكل والاعتماديات الجديدة وتوسيع CI.

- [ ] T001 Create the plan's new directory skeleton with `.gitkeep`: `packages/noor_identity/noor_identity/schemas/`, `packages/noor_identity/tests/`, `packages/noor_sso/python/noor_sso/`, `packages/noor_sso/node/`, `packages/noor_sso/tests/`, `packages/noor_runtime/`, `config/identity/noor/`, `platforms/nmis/full/`, `platforms/quick-analysis/`, `platforms/_snapshots/`, `tools/snapshot/allowlists/`, `tools/surfaces/`, `samples/synthetic/qa-rfp-001/`, `samples/synthetic/atpas-activities/`, `samples/synthetic/radar/`
- [ ] T002 [P] Create `packages/noor_identity/pyproject.toml` و`packages/noor_sso/pyproject.toml` و`packages/noor_runtime/pyproject.toml` (Python >=3.11): `jsonschema` و`cryptography` **بإصدار مثبّت** فقط، بلا مكتبة شبكة؛ و`packages/noor_sso/node/package.json` بلا اعتماديات (`node:crypto` المدمج، ESM)
- [ ] T003 [P] Add ignore rules to `.gitignore`: `config/identity/*/build/`، `noor_staging/`، `**/qa/` تحت `noor_data/`، وأي `*.pem`/`*.key`؛ دون تجاهل `config/identity/noor/profile.json` و`RIGHTS.md`
- [ ] T004 [P] Create license register `THIRD_PARTY_LICENSES.md` (المبدأ XIII، FR-027): لكل اعتمادية جديدة (`cryptography`، Playwright المحلي، Ollama، حزمة خادم tus، `tus-js-client`) الاسم والإصدار والرخصة ومصدرها وتاريخ الرجوع، و«يحتاج تحقق من المصدر الرسمي» لما لم يُتحقق منه
- [ ] T005 **(2026-10-27: ⛔ قرار مالك معلّق قبل خطوة `verify`: R4 يقول إن التعديلات اللاحقة داخل المستودع «لا تغيّر البيان»، بينما `verify --all` يقارن البيان بالشجرة الحالية فيفشل بعد أي تعديل مشروع. المقترح: التحقق من البيان على التزام الاستيراد نفسه، وفحص الفروق اللاحقة بـ `scan_public_repo.py --diff`)** Extend `.github/workflows/noor-v2.yml`: pytest لـ `packages/noor_identity` و`packages/noor_sso` و`packages/noor_runtime` و`platforms/` و`tests/e2e/`؛ و`node --test` لـ `packages/noor_sso/node` و`platforms/radar` و`platforms/quick-analysis`؛ و`python -m tools.snapshot verify` لكل بيان في `platforms/_snapshots/`؛ وفحص `tools/scan_public_repo.py`. لا يُعلَّم مكتملًا قبل حسم 001 T004 (أداة lint)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: العقود، ونواة الجلسة في البيت، والوكيل، والحراس المشتركة، وسجل المنصات، والغلاف، والهوية الدنيا، وأدوات التجهيز، واستلام اللقطات.

**⚠️ CRITICAL**: لا تبدأ أي قصة قبل اكتمال الأقسام (أ)–(و). القسم (ز) «استلام اللقطات» **لا يحجب القصص كلها**: مهام كل منصة في القصص تنتظر دخول لقطتها هي فقط (انظر Dependencies).

### (أ) قرارات المالك

- [ ] T006 (م. يوسف) In `specs/002-full-noor-suite/tasks.md` record each pending owner decision 3–11 (and 10أ per platform) in «سجل البوابات» in `specs/002-full-noor-suite/tasks.md` as it is decided — القرار نصًا كما قاله المالك وتاريخه؛ ثم تُفك علامة ⛔ عن مهامه فقط. أي قرار يغيّر المتطلبات يُحدَّث في `spec.md` ثم `plan.md` ثم هنا (المبدأ XI)

### (ب) العقود (المبدأ VI — شرط حكم PASS في plan.md)

- [x] T007 **(2026-10-27: نُسخت العشرة واختبار الانحراف أخضر)** [P] Copy the ten 002 schemas unchanged (التسعة + `open-approval.schema.json`) from `specs/002-full-noor-suite/contracts/*.schema.json` to `packages/noor_contracts/noor_contracts/schemas/` and extend `packages/noor_contracts/tests/test_schema_drift.py` to cover them (تطابق البايتات)
- [ ] T008 **(2026-10-27: جزئي: قبول/رفض لكل عقد من العشرة؛ اختبارات المُنتِج الحقيقي تُضاف مع مهام المُنتِجين)** [P] Write failing schema tests `packages/noor_contracts/tests/test_schemas_002.py`: لكل عقد من العشرة عينة صحيحة تُقبل، ورفض حقل زائد، وإصدار غير معروف (`/v2`)، ومسار مطلق في أي حقل نصي؛ وقاعدة README 6: مفتاح يجمع `check_result.*` و`approval_state.*` ⇒ رفض. **جدول مُنتِج/مستهلك للعقود العشرة** (كل صف: ناتج المُنتِج الحقيقي يجتاز المخطط والمُتحقِّق، والمستهلك يرفض حقلًا زائدًا ومسارًا مطلقًا وإصدارًا غير معروف): `principal` (T016 ⇐ T024/T026) · `authz-decision` (T022 ⇐ `authz_client` في T024/T026) · `desktop-event` (T079 ⇐ T081) · `platform-status` (T030 ⇐ T036) · `provider-config` (T129 ⇐ T127) · `identity-profile` (T033 ⇐ T032 وT125) · `labels` (T032 ⇐ T113 البيت وT114–T118 المنصات الأربع وATPAS؛ كل مستهلك يتحقق من `labels.ar.json` بالمخطط عند البدء ويفشل بدونه) · `snapshot-manifest` (T038 fingerprint ⇐ T038 verify) · `qa-analysis` (T101 ⇐ مستهلك البيت في T101 نفسها) · `open-approval` (بوابة JoUReady في T075 ⇐ الغلاف في T075)؛ كل مهمة مُنتِج أو مستهلك مذكورة تضيف اختبارها في ملفها
- [x] T009 **(2026-10-27: مُنجز: قاعدة 1 الموسّعة واستثناء `provider-config.endpoint`)** [P] Write failing validator-rule tests `packages/noor_contracts/tests/test_validate_rules_002.py`: قاعدة 1 الموسّعة تكشف مسار POSIX مطلقًا (`^/[^/]`، مثل `/etc/x`) وUNC وحرف قرص و`file:`، مع استثناء صريح لحقل `provider-config.endpoint` وحده؛ ولا تكسر عينات 001
- [x] T010 **(2026-10-27: مُنجز: العقود العشرة مسجّلة واختبارات 001 خضراء)** Implement in `packages/noor_contracts/noor_contracts/validate.py`: تسجيل العقود العشرة، وقاعدة 1 الموسّعة، وقواعد المستهلك 1–6 من `contracts/README.md` حيث تُفحص بلا سياق تشغيل، لاجتياز T007–T009 مع بقاء اختبارات 001 خضراء (SC-010)

### (ج) نواة الجلسة في البيت (R2، data-model.md)

- [x] T011 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing session tests `platforms/nmis/tests/test_sso_sessions.py`: المعرّف 256 بت، و«`sid_hash` SHA-256 سداسي — المعرّف نفسه لا يُخزَّن؛ يُخزَّن تجزيئه فقط»؛ `idle_expires_at` = `last_seen_at` + 30 دقيقة؛ `absolute_expires_at` = `created_at` + 8 ساعات «لا يُمدَّد»؛ `state` ∈ {`active`,`logged_out`,`expired`,`revoked`} و«لا عودة إلى `active`»؛ تدوير المعرّف عند الدخول؛ أي انتقال من `active` يُبطل كل `PlatformSession` و`DesktopHandle` المشتقة؛ «`last_seen_at` يُحدَّث عند أي طلب يمر بالبيت أو وكيله»: استعمال مستمر لمنصة عبر الوكيل يمنع انتهاء الخمول، وتوقفه 30 دقيقة ينهي الجلسة؛ `theme_pref` ∈ {`system`,`light`,`dark`}؛ ملف `noor_sid` host-only على `noor.localhost` و`HttpOnly` و`SameSite=Strict`
- [x] T012 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Extend `platforms/nmis/noor_registry/db.py` (قاعدة جديدة فقط، لا ترحيل على قاعدة حية): جداول `system_session` و`platform_session` و`entry_code` و`desktop_launch_ticket` و`desktop_handle` و`access_decision_log` و`platform_entry` و`fr010_run` و`fr010_item` و`qa_eval_result` بقيود data-model.md حرفيًا (`platform_id` ∈ {`nmis_full`,`radar`,`quick_analysis`,`jouready`} لـ PlatformCredential؛ `PlatformSession.state` ∈ {`active`,`revoked`}؛ EntryCode `expires_at` = +60 ث؛ DesktopLaunchTicket `client` = `desktop:atpas` و`expires_at` = +60 ثانية؛ DesktopHandle `state` ∈ {`active`,`locked`}؛ AccessDecisionLog `result` ∈ {`ok`,`no_session`,`expired`,`forbidden`,`bad_platform_key`,`bad_assertion`} و«لا يحفظ `noor_sid` ولا تجزيئه»؛ FR010Item `result` ∈ {`pass`,`fail`,`blocked`})؛ وإضافة `demo_gate_decision` إلى قائمة `subject_type` في Approval (data-model.md؛ إحالة في 001)
- [x] T013 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement session lifecycle in `platforms/nmis/noor_registry/sso.py`: إصدار وتدوير وخروج وإبطال، ومؤقت البيت كل ثانية لتقييم الخمول والحد المطلق، ونشر الانتقال إلى المقابض والجلسات المشتقة، لاجتياز T011
- [x] T014 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing key tests `platforms/nmis/tests/test_sso_keys.py`: غياب `NOOR_HOME_SIGNING_KEY_FILE` أو ملف داخل المستودع ⇒ فشل البدء؛ لا قيمة افتراضية؛ المنصات تحمّل المفتاح العام فقط ولا تملك مسار توقيع
- [x] T015 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing assertion tests `platforms/nmis/tests/test_sso_assertion.py`: صيغة `v1.<base64url(payload)>.<base64url(sig)>`، JSON قانوني (مفاتيح مرتبة، UTF-8، بلا مسافات)، توقيع Ed25519 بمفتاح البيت، `expires_at − issued_at ≤ 5s`، `nonce` فريد لكل تأكيد، الحمولة تجتاز `noor.principal/v1` ولا تحمل معرّف جلسة ولا تجزيئه؛ AssertionBinding (`nonce` ⇐ `psid_hash`) في الذاكرة فقط «لا يُكتب في القاعدة ولا السجلات ولا يغادر البيت» ويُحذف بعد `expires_at`
- [x] T016 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement key loading, canonical signing and the in-memory AssertionBinding in `platforms/nmis/noor_registry/sso.py`، لاجتياز T014–T015

### (د) الوكيل وCSRF في البيت (R2، internal-api §0–§2)

- [x] T017 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing proxy tests `platforms/nmis/tests/test_proxy.py`: التوجيه حسب `Host` لـ `nmis.` و`radar.` و`qa.` و`jr.noor.localhost:5310`، و`Host` غير مسجّل ⇒ 421؛ `__noor/enter?c=` رمز لمرة واحدة 60 ثانية مربوط بالجلسة الأم والمنصة، مستعمل أو منتهٍ أو لمنصة أخرى ⇒ 403، والاستبدال ذري ⇒ `noor_psid` host-only على أصل المنصة ثم توجيه بلا الرمز؛ `noor_psid` على أصل منصة أخرى ⇒ رفض؛ حذف `Cookie` وكل `X-Noor-*` و`X-User-Email` و`Authorization` الواردة قبل إضافة `X-Noor-Assertion`؛ طلب يغيّر حالة بـ `Origin` ≠ أصل المنصة ⇒ رفض؛ الإبطال الأم يُبطل `noor_psid` فورًا؛ كل طلب يمرره الوكيل يحدّث `last_seen_at` للجلسة الأم (يُنفَّذ في T018 عبر T013)
- [x] T018 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement `platforms/nmis/noor_registry/proxy.py` (loopback فقط، upstream من سجل المنصات)، لاجتياز T017
- [x] T019 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing Origin tests `platforms/nmis/tests/test_origin_check.py` (الملاحظة الملزمة من تجربة العزل): كل مسار متصفح يغيّر حالة في البيت يرفض `Origin` الغائب أو `null` أو أصل أي منصة (`radar.noor.localhost:5310` وغيره)، ويقبل أصل البيت فقط، إلى جانب رمز CSRF القائم (001 T023)؛ ويوسَّع حزام 001 `platforms/nmis/tests/test_routes_authz.py` ليثبت فحص `Origin` على كل مسار حالة من `app.url_map` (إحالة في 001)
- [x] T020 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement the Origin check in `platforms/nmis/noor_registry/security.py`، لاجتياز T019 دون كسر اختبارات 001
- [x] T021 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing internal-authz tests `platforms/nmis/tests/test_internal_authz.py`: `Authorization: Noor-Platform <key>` بمقارنة زمن ثابت؛ **وجود أي `Origin` ⇒ رفض** (لا مطابقة)؛ تأكيد بتوقيع غير البيت أو منتهٍ ⇒ رفض؛ `platform_id` ≠ المنصة الطالبة ⇒ رفض؛ `nonce` غير موجود في الربط، أو جلسة منصة أو أم غير نشطة، أو `user_id` ≠ مالك الجلسة ⇒ `allowed: false`؛ فعل غير مسجّل للمنصة ⇒ `allowed: false`؛ الرد يجتاز `noor.authz-decision/v1`؛ كل قرار يُكتب في AccessDecisionLog بلا مفتاح ولا تأكيد ولا جلسة؛ `/internal/*` لا يمر بالوكيل؛ ومصفوفة FR-005 (4 أدوار × 5 منصات) مرمَّزة في سجل الأفعال: لكل خلية الأفعال المسموحة، وكل فعل خارجها ⇒ `allowed: false`
- [x] T022 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement `POST /internal/authz/check` and the per-platform action registry in `platforms/nmis/noor_registry/sso.py` فوق `authz.authorize` القائمة (المبدأ I)، لاجتياز T021؛ الاحتفاظ بسجل التفويض 30 يومًا (مقترح data-model.md) ثم حذفه

### (هـ) الحراس والوقت التشغيلي المشتركة (R2، R8، R12)

- [x] T023 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing Python verifier tests `packages/noor_sso/tests/test_verify.py`: ترتيب التحقق في internal-api §1 (الصيغة ⇒ التوقيع بالعام ⇒ المخطط ⇒ `platform_id` ⇒ `issued_at ≤ now+2s` و`now < expires_at` و≤5 ث ⇒ `nonce` غير مستعمل)، أي فشل ⇒ 401 بلا تفاصيل؛ إعادة الـ `nonce` ⇒ 401؛ تأكيد بمفتاح آخر ⇒ 401
- [x] T024 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement `packages/noor_sso/python/noor_sso/verify.py` + Flask guard `packages/noor_sso/python/noor_sso/flask_guard.py` + FastAPI dependency/ASGI middleware `packages/noor_sso/python/noor_sso/fastapi_guard.py` + authz client `packages/noor_sso/python/noor_sso/authz_client.py`، لاجتياز T023
- [x] T025 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing Node verifier tests `packages/noor_sso/tests/verify.test.mjs` (`node --test`) بالحالات نفسها في T023
- [x] T026 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement `packages/noor_sso/node/verify.mjs` + `packages/noor_sso/node/http_guard.mjs` (غلاف `node:http`) + `packages/noor_sso/node/express_guard.mjs` + `packages/noor_sso/node/authz_client.mjs`، ESM بلا اعتماديات، لاجتياز T025
- [x] T027 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** [P] Write failing runtime tests `packages/noor_runtime/tests/test_runtime.py` و`packages/noor_runtime/tests/netguard.test.mjs`: `NOOR_EDITION = "hackathon"` ثابت في الكود ولا يغيّره متغير بيئة؛ أي عنوان غير loopback في إعداد ⇒ فشل البدء؛ حارس Node يُحمَّل بـ `--import` ويرفض `net.connect`/`dns.lookup` لغير loopback
- [x] T028 **(2026-10-27: مُنجز؛ نقد Codex الأمني طُبّق)** Implement `packages/noor_runtime/noor_runtime/edition.py` و`edition.mjs` و`netguard.mjs`، وإعادة استعمال `tests/support/no_network` لحارس Python، لاجتياز T027

### (و) سجل المنصات والغلاف والهوية الدنيا والتجهيز

- [ ] T029 **(2026-10-27: جزئي: تحميل السجل من بيانات + loopback + `platform-status/v1`؛ قرار `demo_gate` وApproval لم يُبنيا)** [P] Write failing registry tests `platforms/nmis/tests/test_platforms_registry.py`: PlatformEntry بقيوده حرفيًا (`upstream` «loopback فقط، غير ذلك ⇒ فشل البدء»؛ `run_state` ∈ {`running`,`stopped`,`unavailable_on_device`,`not_cleared_for_demo`}؛ `maturity` ∈ {`L0`..`L3`} «المستوى الفعلي لا المستهدف»؛ `provider_mode` ∈ {`local`,`cloud`,`none`}؛ `demo_gate` ∈ {`passed`,`failed`,`at_risk`,`pending`} «يُضبط بقرار مسجّل في مواعيد FR-031 فقط»)؛ `running` لا يعني «عاملة»؛ `passed` يتطلب كل بنود FR-010 `pass` في آخر FR010Run على `snapshot_tree_sha256` الحالي + مرجع دليل الإغلاق + تعداد مسارات أخضر + كتالوج أسطح معتمد + ISO-REAL للويب، وإلا `not_cleared_for_demo`؛ `fr010_result` فارغ ⇒ «لم يُقَس بعد»؛ تغيير `demo_gate` يكتب Approval `demo_gate_decision` من م. يوسف؛ الناتج يجتاز `noor.platform-status/v1`
- [ ] T030 **(2026-10-27: جزئي كما في T029)** Implement `platforms/nmis/noor_registry/platforms_registry.py`، لاجتياز T029
- [ ] T031 **(2026-10-27: كُتبت واجتازت؛ اختبار الرابط الرمزي متخطّى على ويندوز (لا صلاحية إنشاء روابط))** [P] Write failing identity tests `packages/noor_identity/tests/test_build.py`: ملف تعريف غائب أو لا يجتاز `noor.identity-profile/v1` أو ملف مُشار إليه مفقود أو رابط رمزي خارج `NOOR_IDENTITY_DIR` ⇒ فشل؛ التباين محسوب لكل زوج نص/خلفية وشارة حالة في الوضعين ويفشل البناء دون 4.5:1 (3:1 للنص الكبير)؛ `labels.ar.json` يجتاز `noor.labels/v1` ولكل قيمة `text_ar` و`aria_label_ar` و`shape` و`color_token`، و`check_result.*` و`approval_state.*` مفتاحان منفصلان؛ **الشعار**: ملف مُشار إليه مفقود ⇒ فشل البدء، وملف موجود لكنه تالف ⇒ لا فشل والاسم نصًا عند العرض (data-model.md)
- [x] T032 **(2026-10-27: مُنجز: البناء والتباين في الوضعين وجدول التسميات)** Implement `packages/noor_identity/noor_identity/build.py` (`python -m noor_identity build` ⇒ `noor-tokens.css` للوضعين مع `@font-face` محلي، و`noor_tokens.json`، وقيم أنماط Word، في `NOOR_IDENTITY_DIR/build/`) و`packages/noor_identity/noor_identity/labels.ar.json` بجدول FR-023 (المنصات الخمس؛ «منافسة»؛ «مرشَّحة / مقبولة / مرفوضة»؛ «مطابق / غير مطابق / تعذّر التحقق»؛ «مقترح / معتمد»)، لاجتياز T031
- [x] T033 **(2026-10-27: مُنجز: شعار نصي وTajawal OFL؛ ملف الشعار لم يُسلَّم)** Write `config/identity/noor/profile.json` («منظومة النور»، الاسم المختصر «النور»، «شركة النور للمقاولات» كيانًا افتراضيًا، `primary` = `#0b5d4b` للوضع الفاتح ولوحة داكنة) **بشعار نصي** (`logo` فارغ) **وخط بديل مسمّى** (`font.fallback`) إلى أن تُثبت الحقوق، و`config/identity/noor/RIGHTS.md` بحالة كل أصل «غير محسوم» (FR-027)
- [ ] T034 (م. يوسف يسلّم ملف الشعار) Add the logo file and Tajawal font files to `config/identity/noor/` and reference them in `profile.json`؛ الحقوق: الشعار بإقرار ملكية م. يوسف (القرار 11-أ، 2026-10-27)، ويُسجَّل في `config/identity/noor/RIGHTS.md` **للملف المسلَّم تحديدًا**: اسم الملف وبصمته SHA-256، والمالك، وتاريخ الإقرار، والاستعمال المسموح (العرض والبيع والمستودع العام)، قبل دخوله المستودع؛ وTajawal بترخيص SIL OFL 1.1 مع ربط `OFL.txt` (`platforms/nmis/noor_registry/static/fonts/OFL.txt` من 001 T031) بملفات الخط المضمَّنة وبصماتها (FR-027). حتى تسليم ملف الشعار يبقى الشعار النصي
- [ ] T035 **(2026-10-27: جزئي: القائمة بالخمس وحالاتها ونضجها ووضع مزودها؛ الإطار و`postMessage` لم يُبنيا (ينتظران الوكيل))** [P] Write failing shell tests `platforms/nmis/tests/test_shell.py`: القائمة الجانبية بالمنصات الخمس بأسمائها الثابتة وحالتها ونضجها ووضع مزودها؛ الإطار `<iframe sandbox="allow-scripts allow-same-origin allow-forms allow-downloads">` على أصل المنصة؛ `postMessage` بقائمة مغلقة (`noor:go-home`، `noor:title`) مع فحص `origin` ولا رسالة تنفّذ فعلًا؛ منصة متوقفة ⇒ «متوقفة» ولا تنكسر البقية؛ ATPAS على غير Windows ⇒ «غير متاح على هذا الجهاز»؛ بيان النضج يُبقي إفصاحات 001 FR-020
- [ ] T036 **(2026-10-27: جزئي: الغلاف وصفحة كل منصة بإفصاح صادق؛ بلا إطار حتى الوكيل)** Implement `platforms/nmis/noor_registry/views_shell.py` + `platforms/nmis/noor_registry/templates/shell/` (ترويسة المنظومة من `noor-tokens.css`، القائمة، الإطار، بيان النضج والإفصاح)، لاجتياز T035
- [x] T037 **(2026-10-27: مُنجز عبر Codex؛ نقد Codex أربع جولات: NOT-READY ⇐ NOT-READY ⇐ NOT-READY ⇐ READY-AFTER-FIXES، وآخر ملاحظة (استئناف الاستيراد المقطوع قبل النقل) أصلحها Claude باختبار؛ متبقٍّ مؤجل: مخطط `snapshot-manifest` يقبل تكرار أداة الفحص — تعديل عقد يمر بالمواصفة أولًا، والأداة تمنعه عمليًا)** [P] Write failing snapshot-tool tests `tools/tests/test_snapshot.py`: `NOOR_STAGING_DIR` داخل المستودع ⇒ رفض؛ قائمة السماح تحذف كل ما سواها؛ ممنوعات FR-007 ثابتة تُرفض ولو وردت في القائمة (`.env*` عدا `.env.example`، المفاتيح، `security_vault*`، `*.db`/`*.sqlite*`، ملفات تعريف المتصفح، نسخ n8n وقاعدته، مكتبة ATPAS، `dist/` `build/` `output/`، Excel وكلمات المرور، وأي مجلد تقارير خاصة أو ملف تقرير فحص كامل)؛ و`NOOR_PRIVATE_REPORTS_DIR` داخل المستودع أو داخل `NOOR_STAGING_DIR` ⇒ رفض؛ بصمة الشجرة = SHA-256 لقائمة مرتبة من (مسار POSIX نسبي، حجم، sha256) بـ UTF-8 وNFC؛ تعديل بايت واحد ⇒ فشل `verify`؛ تعديل بعد `scanned` يعيد الحالة إلى `staged`؛ البيان يجتاز `noor.snapshot-manifest/v1` بلا مسار مطلق؛ `scans[]` تتطلب الأدوات الثلاث
- [x] T038 **(2026-10-27: مُنجز عبر Codex؛ نقد Codex أربع جولات: NOT-READY ⇐ NOT-READY ⇐ NOT-READY ⇐ READY-AFTER-FIXES، وآخر ملاحظة (استئناف الاستيراد المقطوع قبل النقل) أصلحها Claude باختبار؛ متبقٍّ مؤجل: مخطط `snapshot-manifest` يقبل تكرار أداة الفحص — تعديل عقد يمر بالمواصفة أولًا، والأداة تمنعه عمليًا)** Implement `tools/snapshot/{__main__,stage,select,scan,fingerprint,verify}.py` — كل أمر على مجلد التجهيز يطبع الملخص المعتم فقط ويكتب التفاصيل في `NOOR_PRIVATE_REPORTS_DIR` (حدّ Claude)، وأمر `mark-sanitized` يقرأ قائمة م. يوسف المعتمدة للملفات المنقّحة، و`tools/snapshot/allowlists/` (ملف لكل منصة يُملأ يوم تجهيزها)، لاجتياز T037
- [x] T039 **(2026-10-27: مُنجز عبر Codex؛ نقد Codex أربع جولات: NOT-READY ⇐ NOT-READY ⇐ NOT-READY ⇐ READY-AFTER-FIXES، وآخر ملاحظة (استئناف الاستيراد المقطوع قبل النقل) أصلحها Claude باختبار؛ متبقٍّ مؤجل: مخطط `snapshot-manifest` يقبل تكرار أداة الفحص — تعديل عقد يمر بالمواصفة أولًا، والأداة تمنعه عمليًا)** [P] Write failing scanner tests `tools/tests/test_scan_forbidden_ids.py` بأسماء وهمية فقط: قائمة من `NOOR_BLOCKLIST_FILE` بصيغها (بلا «ال»، تهجئات لاتينية)؛ فحص `docProps/core.xml` و`app.xml` وPDF `Info` وبيانات الصور الوصفية؛ إخراج قائمة أصول ثنائية للمراجعة البصرية؛ الاستثناءات من `tools/scan_allowlist.json` فقط (`.specify/memory/`، `specs/`، ملف القائمة، اختبارات الفحص)
- [x] T040 **(2026-10-27: مُنجز عبر Codex؛ نقد Codex أربع جولات: NOT-READY ⇐ NOT-READY ⇐ NOT-READY ⇐ READY-AFTER-FIXES، وآخر ملاحظة (استئناف الاستيراد المقطوع قبل النقل) أصلحها Claude باختبار؛ متبقٍّ مؤجل: مخطط `snapshot-manifest` يقبل تكرار أداة الفحص — تعديل عقد يمر بالمواصفة أولًا، والأداة تمنعه عمليًا)** Extend `tools/scan_public_repo.py` لاجتياز T039 (R10): يُعتمد اسم المتغير القائم `NOOR_BLOCKLIST_FILE` (لا اسم ثانٍ)؛ `--require-blocklist` إلزامي في كل فحص قبل الاستيراد وقبل أي إرسال إلى أداة خارجية (يفشل الفحص بلا القائمة)؛ ووضع إخراج افتراضي `--opaque` يطبع على الشاشة **ملخصًا معتمًا فقط** (عدد النتائج لكل قاعدة، ومعرّف الملف المعتم = أول 12 حرفًا من SHA-256) بلا أسماء ملفات ولا مسارات ولا أسطر ولا نص مطابق، ويكتب التقرير الكامل في `NOOR_PRIVATE_REPORTS_DIR/<platform>/` لـ م. يوسف وحده (حدّ Claude، X1 وN2)
- [ ] T041 **(2026-10-27: م. يوسف ينشئ الملف بنفسه خارج المستودع (R1)؛ الأداة تقرأ `utf-8-sig` فيقبل ملف PowerShell 5.1)** Create the forbidden-identity file named by `NOOR_BLOCKLIST_FILE` (خارج المستودع) بالقائمة النهائية (القرار 11-ب): أسماء الهوية السابقة (العربية واللاتينية)؛ وقاعدة الاستبدال في كل تنقيح (T045، T049، T057، T060): كل موضع للهوية السابقة يُستبدل بهوية «النور» من ملف التعريف (لا يُحذف فيترك فراغًا)، ويُثبت الفحص صفر بقايا
- [ ] T042 Implement `launcher/noor-suite.ps1`: يرفض البدء ويسمّي المتغير الناقص من جدول «متغيرات البيئة»، أو ملف هوية غائبًا/تالفًا (US4-2)، أو إعداد `cloud` (US5-2)؛ يبني الرموز؛ يشغّل البيت (5310) والمنصات الويب المستلمة على منافذ plan.md (5311، 4318، 5312، 5313، 5314) على loopback مع حارس الشبكة؛ لا يستبدل `launcher/noor-demo.ps1` (001)

### (ز) استلام اللقطات (R4، FR-006، FR-007) — بوابات المالك

> كل استيراد: تجهيز في `NOOR_STAGING_DIR` ⇐ تنقيح وإغلاق التعرض هناك ⇐ `tools/scan_public_repo.py` + قائمة الهويات + البيانات الوصفية + مراجعة بصرية (`EXP-PRIOR-IDENTITY`) ⇐ بصمة ⇐ نسخ المطابق ⇐ `python -m tools.snapshot verify`. **لا شيء من مجلد التجهيز يُرسل إلى MiniMax أو Codex** (R14). صيغة `SOURCE.md`: وسم بديل للمصدر (القرار 8).

- [ ] T043 Write `platforms/<name>/SOURCE.md` template (وسم المصدر، بصمة الشجرة، تاريخ النسخ، المضمَّن والمستبعد، مراجع `exposures_closed`) بوسم بديل للمصدر، والمرجع الحقيقي (المستودع والالتزام) يبقى عند م. يوسف خارج المستودع (القرار 8)

**NMIS الكامل (NMIS-N11، R1)**

- [ ] T044 (م. يوسف) Gate `EXP-NMIS-PASSWORDS` **2026-10-28 مساءً**: إزالة القيم + فشل الإقلاع بلا متغيرات + **تدوير على النسخة الحية** = **001 T007** (يُسجَّل هناك)
- [ ] T045 (م. يوسف؛ Claude بأوامر آلية فقط: `git archive`، انتقاء، فحص، بصمة، وسكربتات تنقيح بقواعد صريحة — بلا فتح محتوى، plan.md «حدّ Claude») Stage NMIS full in `NOOR_STAGING_DIR/nmis_full/<YYYYMMDD-HHMM>/` via `git archive` from the owner's reference (خارج المستودع): N3 ممنوعات؛ N0 إزالة كلمات المرور؛ N5 وحدة أسرار من البيئة بدل الخزنة؛ N7 Telegram معطّل؛ N4 إزالة الهوية الافتراضية؛ الاستماع `127.0.0.1:5311` بدل `::` (N6)؛ قاعدة فارغة؛ `tools/snapshot/allowlists/nmis_full.txt`؛ فحص وبصمة
- [ ] T046 Import NMIS full into `platforms/nmis/full/` + `platforms/_snapshots/nmis_full.json` + `platforms/nmis/full/SOURCE.md` بعد T044 = PASS وT045 نظيف؛ وأضف أسماء أسرار وحدة N5 إلى جدول «متغيرات البيئة» أعلاه
- [ ] T047 (م. يوسف) First baseline run of imported NMIS full tests بأمر المالك (N10): الأمر والبيئة والالتزام والنتيجة والقيود في «سجل البوابات»؛ لا يُكتب العدد في مكان آخر (المبدأ X)؛ السجل في `specs/002-full-noor-suite/tasks.md`

**الرادار (RAD-01/02/06/07)**

- [ ] T048 (م. يوسف) Gate RAD-02 (فحص التاريخ وتثبيت المصدر) = **001 T008**؛ هدف 2026-10-28 مساءً (plan.md 002)
- [ ] T049 Stage radar in `NOOR_STAGING_DIR/radar/`: بلا أي قاعدة حقيقية؛ تعطيل التشغيل الحي وPlaywright/CDP الحي وأي تنزيل؛ لا ترحيل تلقائي عند الإقلاع (RAD-07)؛ الواجهة على 5312 بدل 3000 مع تعديل افتراض الخدمة (RAD-03)؛ الخدمة 4318؛ `tools/snapshot/allowlists/radar.txt`؛ فحص وبصمة
- [ ] T050 Import radar into `platforms/radar/` + `platforms/_snapshots/radar.json` + `SOURCE.md` بعد T048 = PASS
- [ ] T051 Implement synthetic DB generator `samples/synthetic/radar/generate.mjs` بمخطط الرادار المستورد إلى `NOOR_RADAR_DB` فقط (يرفض أي مسار قاعدة تشغيل)، بجهات وأرقام وتصنيفات خيالية تغطي بنود RAD-F01..F09، ومدخل في `samples/synthetic/radar/RIGHTS.md` (فريق الهندسة يراجع الأسماء)

**JoUReady (JR-D1، JR-D3/D4، JR-D6، JR-R)**

- [ ] T052 (م. يوسف) Grant read access to the private JoUReady repository for the reference commit (R13)، وسجّل الإذن ونطاقه في «سجل البوابات» في `specs/002-full-noor-suite/tasks.md`
- [ ] T053 (م. يوسف) Gate `EXP-JR-TEMPLATE` (لقطة بلا تاريخ + فحص محتوى القالب + إزالة تلميح المفتاح من إعداد المزودين) = **001 T071**؛ هدف 2026-10-30
- [ ] T054 Stage JoUReady in `NOOR_STAGING_DIR/jouready/`: المكتبة الحتمية + الخادم + البوابة + ثلاثية الأدلة + المواصفات والاختبارات؛ **بلا مشغّل الوكلاء**؛ إزالة إحالة `opencode-go`؛ تنقيح القالب؛ المزودون السحابيون معطّلون؛ الاستماع `127.0.0.1:5314` بدل `0.0.0.0:8080`؛ `tools/snapshot/allowlists/jouready.txt`
- [ ] T055 Import JoUReady into `platforms/jouready/` + `platforms/_snapshots/jouready.json` + `SOURCE.md` **فقط بعد** T053 = PASS واجتياز `EXP-JR-AUTH` على اللقطة في التجهيز (T072–T076 في US1)؛ ثم أول تشغيل لاختباراتها بأمر المالك (JR-D10)

**ATPAS (ATP-D0..D10، ATP-R)**

- [ ] T056 (م. يوسف) Gate `EXP-ATPAS-LICENSE` (وقف المفاتيح المكشوفة + إبطالها وتدويرها + توثيق نطاق التعرض وخطة التاريخ) = **001 T055**؛ هدف 2026-10-30
- [ ] T057 Stage ATPAS in `NOOR_STAGING_DIR/atpas/`: المحرك + الواجهة المكتبية (ATP-D4 المعدّل)؛ ATP-D3 ممنوعات؛ تحقق الترخيص بمفتاح عام Ed25519 فقط بلا سر توقيع (ATP-D0)؛ وضع داخلي متسق في بوابة البدء والمحرك (ATP-D5)؛ إسقاط `output_file` من JSON وCSV وفهرس SQLite (ATP-D8)؛ الحالة من `NOOR_ATPAS_DATA_DIR` لا `%APPDATA%/ATPAS/` (ATP-R)؛ مسار المكتبة من `NOOR_ATPAS_CONTENT_DIR` (ATP-D7)؛ فحص الأصول الثنائية والقوالب؛ `tools/snapshot/allowlists/atpas.txt`
- [ ] T058 Import ATPAS into `platforms/atpas/` + `platforms/_snapshots/atpas.json` + `SOURCE.md` بعد T056 = PASS؛ ثم أول تشغيل لاختباراتها بأمر المالك (ATP-D9)

**التحليل السريع (QA-U3، QA-U8، R7)**

- [ ] T059 (م. يوسف؛ Claude ينفّذ أوامر النسخ فقط ولا يفتح الملفات المنسوخة — الـ prompts وتصدير السير ومولّد التقارير لا تُفتح قبل مراجعة م. يوسف، plan.md «حدّ Claude») Copy from the quick-analysis server per QA-U8 only — الوصول: إعداد SSH قائم على جهاز التطوير بمضيف ومفتاح في `~/.ssh` (القرار 11-ج؛ لا يُقرأ المفتاح ولا يُطبع)؛ والمصدر البديل أو المكمّل: **النسخة الاحتياطية المحلية** (وُجدت 2026-10-27؛ أحدثها بتاريخ 2026-10-23، ومسارها في INVENTORY خارج المستودع) وفيها مولّد التقارير وتصدير السير وقاعدة n8n؛ **لا تُنسخ منها قاعدة n8n ولا `env_keys` ولا تُفتح**، وتصدير السير يُنقّح من أي بيانات اعتماد قبل التجهيز بالقواعد نفسها: قراءة فقط ونسخ إلى التجهيز (قراءة ونسخ عبر SSH، بلا تعديل ولا إعادة تشغيل ولا `.env` ولا `env_keys` ولا قاعدة n8n): مولّد التقارير العربي، وتصدير السير الثلاث JSON بلا بيانات اعتماد وتنفيذات، والـ prompts، إلى `NOOR_STAGING_DIR/quick-analysis/`؛ مع ServerAccessLog خارج المستودع (`at_start`/`at_end`، `operator`، `files_copied[]` ببصماتها، `commands_run[]`). إن تعذّر النسخ من المصدرين حتى **2026-10-28 مساءً** تُعلَّم المنصة `at_risk` (FR-031)
- [ ] T060 (Claude بأوامر آلية فقط حتى تعليم م. يوسف للكود منقّحًا) Stage the local quick-analysis code (`mcp-server` + `tender-ui`، بصماته الخمس مطابقة لملف التسليم) مع ما نُسخ في T059 في المجلد نفسه؛ إزالة Cloudflare Access و`X-User-Email` و`IS_DEV` و`whoami` المبني على الترويسة و`logo-former-identity` والمسارات الصلبة؛ إزالة webhooks n8n مع n8n (القرار 3: منفّذ محلي داخل Express)؛ `tus-js-client` بإصدار مثبّت محليًا بدل `unpkg.com`؛ `tools/snapshot/allowlists/quick-analysis.txt`
- [ ] T061 **لا إعادة بناء** لمولّد التقارير (القرار 5: الوصول إلى السيرفر متاح ونسخة محلية موجودة)؛ تُقارن بصمات ملفات مولّد التقارير بين السيرفر والنسخة الاحتياطية المحلية (2026-10-23)؛ إن اختلفا يُسجَّل الفرق خارج المستودع ويختار م. يوسف المصدر المرجعي **قبل** بصمة اللقطة في T060؛ التطابق ليس شرط قبول
- [ ] T062 Import quick-analysis into `platforms/quick-analysis/` + `platforms/_snapshots/quick-analysis.json` + `SOURCE.md` **فقط بعد** إغلاق `EXP-QA-ROUTES-TUS` بدليل على اللقطة في التجهيز (T082–T085 في US1) واعتماد م. يوسف للدليل

**Checkpoint**: الأساس جاهز؛ تبدأ القصص. مهام كل منصة في القصص تنتظر دخول لقطتها (أو تُنفَّذ في التجهيز حيث يُذكر).

---

## Phase 3: User Story 1 — دخول واحد إلى المنصات الخمس (Priority: P1) 🎯 MVP

**Goal**: دخول واحد في البيت يفتح كل منصة مستلمة دون دخول ثانٍ؛ كل مسار في كل منصة يرفض بلا جلسة أو صلاحية؛ الخروج يرفض الكل؛ ATPAS يُفتح من البيت فقط ويقفل ≤5 ثوانٍ.

**Independent Test**: من جلسة واحدة تُفتح المنصات بالترتيب بلا شاشة دخول ثانية، ثم الخروج فتُرفض كلها (quickstart §2–§4).

### Tests for User Story 1 ⚠️ (تُكتب أولًا وتفشل)

- [ ] T063 [P] [US1] E2E test `tests/e2e/test_suite_sso.py`: دخول «مدير العروض» ⇒ فتح كل منصة مستلمة من الغلاف بلا شاشة دخول (US1-1)؛ حساب بلا صلاحية على منصة من القائمة وبالرابط المباشر ⇒ رسالة رفض (US1-2)؛ طلب مباشر على `127.0.0.1:<port>` بلا تأكيد وبمزوَّر ومنتهٍ ومُعاد ⇒ 401 (US1-3)؛ الخروج ثم أي مسار بعد 5 ثوانٍ ⇒ رفض في الكل (US1-4)؛ حساب العرض ⇒ رفض كل تعديل؛ تُشغَّل لكل منصة عند دخولها ولا تُحسب منصة غير مستلمة «اجتازت»؛ **مصفوفة الأدوار** `tests/e2e/test_role_matrix.py`: لكل خلية في FR-005 (مدير العروض، معتمِد المراجعة، مهندس = `member`، عرض = `viewer` × الخمس) فعل مسموح يُقبل وفعل غير مسموح يُرفض، والصلاحية محصورة بالمنافسة (صلاحية على منافسة لا تصلح لأخرى)؛ **انتهاء الجلسة أثناء العمل**: تنتهي الجلسة في منتصف مسار ⇒ يُطلب الدخول من جديد، وقرار الاعتماد المسجَّل قبلها باقٍ كما هو في سجل القرارات (الحالة الحدّية في spec)
- [ ] T064 [P] [US1] Cross-origin test `tests/e2e/test_suite_isolation.py` (quickstart §2أ) بالوكيل والبيت الحقيقيين: من إطار كل منصة ويب `parent.document` ⇒ `SecurityError`، و`document.cookie` بلا `noor_sid`، وطلب حالة إلى البيت ⇒ مرفوض بفحص `Origin`
- [ ] T065 [P] [US1] Provider-agnostic route-enumeration contract `tests/support/route_enum.py`: واجهة واحدة تقارن «المسارات المستخرجة آليًا» بـ«المسارات المختبَرة» لكل منصة وتفشل عند أي فرق (SC-003)

### Implementation for User Story 1 — NMIS الكامل (بعد T046)

- [ ] T066 [US1] Write failing route test `platforms/nmis/full/tests/test_noor_routes_authz.py`: على `app.url_map` الفعلي، كل مسار ⇒ 401 بلا تأكيد، ويُرفض لدور `viewer` في كل تعديل وتنزيل غير مسموح (NMIS-R، 001 FR-022)، وأفعال المنافسة تمر بـ `/internal/authz/check`
- [ ] T067 [US1] Replace `web_auth` with a global `before_request` from `noor_sso.flask_guard` in `platforms/nmis/full/` (حساب العرض بالدور `viewer` لا `admin_ok`)، وأفعال المنافسة عبر `authz_client`، لاجتياز T066
- [ ] T068 [US1] Register `nmis_full` in `platforms/nmis/noor_registry/platforms_registry.py` (upstream `http://127.0.0.1:5311`، أصل `nmis.noor.localhost:5310`) وأفعاله في سجل الأفعال (T022)

### Implementation for User Story 1 — الرادار (بعد T050)

- [ ] T069 [US1] Determine route extraction on the snapshot: جدول مسارات الخدمة (`node:http` 4318) + مسارات `app/` في vinext — استخراج آلي إن أمكن، وإلا **سكربت** يحلّل المصدر ويُشغَّل مع الاختبار في CI (القائمة المكتوبة يدويًا لا تُقبل، SC-003)؛ سجّل الطريقة وحدودها في `platforms/radar/test/noor-routes.md` (plan.md الأمان 10)
- [ ] T070 [US1] Write failing route test `platforms/radar/test/noor-routes-authz.test.mjs` (`node --test`) بالقائمة من T069 عبر T065
- [ ] T071 [US1] Wrap the service request handler with `noor_sso/node/http_guard.mjs` before routing, and add a vinext server middleware for the UI, in `platforms/radar/`، لاجتياز T070؛ وسجّل `radar` في سجل المنصات (4318 و5312، أصل `radar.noor.localhost:5310`)

### Implementation for User Story 1 — JoUReady (في التجهيز قبل T055، ثم في المستودع)

- [ ] T072 [US1] (بعد اجتياز الفحص وتعليم م. يوسف لكود اللقطة «منقّحًا» في سجل البوابات — حدّ Claude) Write failing route test `jouready` على `app.routes` (يُكتب في التجهيز، ويُستورد مع اللقطة إلى `platforms/jouready/tests/test_noor_routes_authz.py`): كل مسار تشغيل واعتماد واستئناف وقراءة تقرير، ومنه `/api/runs/{rid}/resume` و`/api/gate/*`، ⇒ 401 بلا تأكيد و403 بلا صلاحية على المنافسة
- [ ] T073 [US1] (بعد اجتياز الفحص وتعليم م. يوسف لكود اللقطة «منقّحًا» في سجل البوابات — حدّ Claude) Write failing tests (في التجهيز، ثم `platforms/jouready/tests/test_noor_shadow_paths.py`): `mode` مفروض `shadow` من الخادم ويُتجاهل من الطلب؛ أي مسار للمرحلة 2 ⇒ رفض؛ `root` و`tender` من الطلب خارج `JR_TENDERS_ROOT` أو بـ `..` أو رابط رمزي خارج ⇒ رفض
- [ ] T074 [US1] (بعد اجتياز الفحص وتعليم م. يوسف لكود اللقطة «منقّحًا» في سجل البوابات — حدّ Claude) Add ASGI middleware + a global dependency on every `APIRouter` from `noor_sso.fastapi_guard` in the staged JoUReady server، وفرض `shadow` وقفل المرحلة 2 وحصر `root`/`tender`، لاجتياز T072–T073 (`EXP-JR-AUTH`، JR-D6، JR-R)
- [ ] T075 [US1] Route JoUReady gate approvals through the home (قيد JR-D0، `contracts/internal-api.md` §4): زر «اعتماد» في بوابة JoUReady يرسل `postMessage` بعقد `noor.open-approval/v1` و`targetOrigin` حرفي ولا يكتب شيئًا؛ الغلاف في `platforms/nmis/noor_registry/templates/shell/` يقبلها فقط من `event.origin` = `jr.noor.localhost:5310` و`event.source` = إطار JoUReady الحالي وبعد المخطط والمُتحقِّق، ثم ينتقل إلى صفحة اعتماد البيت بـ `report_id` و`tender_id` (001 T088) التي تحلّ التقرير وتشتق منافسته من السجل وتفوّض عند التحميل وعند POST. اختبارات `platforms/nmis/tests/test_open_approval.py`: الرسالة لا تغيّر أي حالة بنفسها؛ أصل آخر أو مصدر غير الإطار أو حمولة لا تجتاز المخطط ⇒ تُتجاهل وتُسجَّل؛ `tender_id` لا يطابق منافسة التقرير المخزَّنة ⇒ رفض؛ القرار في صفحة البيت يمر بالتفويض و`Origin` وCSRF؛ وبوابة JoUReady لا تملك أي مسار يكتب اعتمادًا
- [ ] T076 [US1] (م. يوسف) Gate `EXP-JR-AUTH` evidence on the staged snapshot: T072–T074 خضراء + `shadow` مثبت + المرحلة 2 مقفلة؛ الحكم في «سجل البوابات» في `specs/002-full-noor-suite/tasks.md` قبل T055 (يبقى اختبار مسارات اعتماد التقرير في البيت في 001 T080)
- [ ] T077 [US1] Register `jouready` in the platform registry (upstream `http://127.0.0.1:5314`، أصل `jr.noor.localhost:5310`) وأفعاله

### Implementation for User Story 1 — ATPAS المكتبي (R3، بعد T058)

- [ ] T078 [P] [US1] Write failing home-side desktop tests `platforms/nmis/tests/test_desktop_sso.py`: `POST /atpas/launch` يتطلب CSRF + `Origin` البيت + صلاحية «بناء» أو «قراءة المخرجات»، ويصدر تذكرة 256 بت لمرة واحدة 60 ثانية ويحفظ `launched_pid` ويمرّرها عبر stdin بقائمة وسائط بلا shell؛ `/internal/desktop/exchange` ذري (`UPDATE … WHERE used_at IS NULL AND expires_at > now`) ويتطلب `pid` = `launched_pid` وعملية حية، واستبدال ثانٍ أو بعد الانتهاء أو PID مختلف ⇒ 403؛ `/internal/desktop/check` و`/events` بـ `Authorization: Noor-Desktop <handle>` ويرفضان أي `Origin`؛ `events` long-poll ≤25 ثانية يُوقَظ **فورًا** بـ `threading.Condition` عند أي انتقال للجلسة ويعيد `noor.desktop-event/v1` (`logout`/`expired`/`revoked`)، و`heartbeat` عند المهلة فقط؛ المؤقت (كل ثانية) ينشر انتهاء الخمول والمطلق؛ المقبض لا يصلح لأي مسار متصفح ولا للوكيل
- [ ] T079 [US1] Implement `platforms/nmis/noor_registry/views_atpas.py` + desktop endpoints in `platforms/nmis/noor_registry/sso.py`، لاجتياز T078 (Windows فقط؛ غيره ⇒ «غير متاح على هذا الجهاز»)
- [ ] T080 [US1] Write failing ATPAS client tests `platforms/atpas/tests/test_noor_desktop.py` (ATP-F10): (أ) الخروج من البيت ⇒ صفحة القفل ظاهرة ≤5 ثوانٍ بخطاف اختبار يسجل وقت التبديل؛ (ب) قتل عملية البيت ⇒ قفل ≤5 ثوانٍ؛ (ج) انتهاء الخمول ⇒ قفل ≤5 ثوانٍ؛ (د) تذكرة مستعملة أو منتهية أو PID مختلف ⇒ رفض؛ (هـ) فعل بناء بعد القفل ⇒ مرفوض؛ (و) بلا تذكرة على stdin خلال 10 ثوانٍ ⇒ رفض البدء برسالة (US1-5)
- [ ] T081 [US1] Implement `packages/noor_sso/python/noor_sso/desktop_client.py` (مقبض، `QThread` long-poll، `POST /internal/desktop/check` متزامن قبل كل فتح/بناء/حفظ/تصدير، احتياط كل 60 ثانية، قفل عند **أي** فشل) وصفحة القفل `QStackedWidget` وبوابة البدء في `platforms/atpas/main.py` (نفس بوابة الوضع الداخلي ATP-D5)، لاجتياز T080


### Implementation for User Story 1 — التحليل السريع (في التجهيز قبل T062، ثم في المستودع)

- [ ] T082 [US1] (بعد اجتياز الفحص وتعليم م. يوسف لكود اللقطة «منقّحًا» في سجل البوابات — حدّ Claude) Write failing route test (في التجهيز، ثم `platforms/quick-analysis/test/noor-routes-authz.test.mjs`) على مكدس موجّه Express: كل `/mcp/*` ورفع tus و`download` ⇒ 401 بلا تأكيد و403 بلا صلاحية؛ لا مسار webhook مستمع (القرار 3)
- [ ] T083 [US1] (بعد اجتياز الفحص وتعليم م. يوسف لكود اللقطة «منقّحًا» في سجل البوابات — حدّ Claude) Write failing hardening tests (في التجهيز): `session_id`/`job_id` بصيغة UUID صارمة قبل أي بناء مسار؛ `save-analysis` يحصر الكتابة في `NOOR_DATA_DIR/qa/`؛ الرفع بحد حجم (المقترح 100 ميغابايت) ونوع `application/pdf` وتوقيع `%PDF-`؛ **ملف PDF تالف أو مقطوع أو محمي بكلمة مرور** ⇒ المهمة تنتهي إلى `failed` برسالة «تعذّر قراءة الكراسة»، ولا يصدر تقرير جزئي ولا يُعرض مكتملًا (الحد الأدنى للاختبارات: فشل قراءة الملفات)
- [ ] T084 [US1] (بعد اجتياز الفحص وتعليم م. يوسف لكود اللقطة «منقّحًا» في سجل البوابات — حدّ Claude) Add `noor_sso/node/express_guard.mjs` as the first `app.use` and replace `whoami` with the verified principal in the staged quick-analysis server، لاجتياز T082–T083 (بنود SECURITY_BACKLOG الخمسة)
- [ ] T085 [US1] (م. يوسف) Gate `EXP-QA-ROUTES-TUS`: دليل البنود الخمسة على اللقطة في التجهيز + بصمة الشجرة المفحوصة؛ أي تعديل بعد الفحص يعيده؛ الحكم في «سجل البوابات» قبل T062
- [ ] T086 [US1] Register `quick_analysis` in the platform registry (upstream `http://127.0.0.1:5313`، أصل `qa.noor.localhost:5310`) وأفعاله

### البوابة الحقيقية للعزل (ISO-REAL، research R2)

- [ ] T087 [US1] (م. يوسف + Claude) ISO-REAL per web platform (NMIS الكامل، الرادار، JoUReady، التحليل السريع) **على متصفح العرض** ومن داخل واجهة المنصة الحقيقية خلف الوكيل الحقيقي: عدم وصول `noor_sid` إلى أصلها، وحجب `parent.document`، ورفض طلب حالة منها إلى البيت، ورفض التأكيد المزوَّر لدى حارسها الحقيقي؛ لكل منصة صف في «سجل البوابات» في `specs/002-full-noor-suite/tasks.md` والفحوص في `tests/e2e/test_suite_isolation.py` على متصفح العرض؛ الفشل ⇒ المنصة «لم تجتز شروط العرض»
- [ ] T088 [US1] Run T063–T064 + every platform route test and record SC-001/SC-003 per received platform in «سجل البوابات» (الأمر والبيئة والالتزام والنتيجة والقيود)

**Checkpoint**: الدخول الموحد يعمل لكل منصة مستلمة؛ ما لم يُستلم يظهر في البيت بحالته.

---

## Phase 4: User Story 2 — المنصات الخمس تعمل بوظائفها (Priority: P1)

**Goal**: كل منصة تؤدي قائمتها في FR-010 على بيانات مصطنعة، وتُسجَّل نتيجة كل بند بصورة.

**Independent Test**: لكل منصة تُنفَّذ قائمة `contracts/fr010-checklists.md` وتُسجَّل `pass`/`fail`/`blocked` بصورة (SC-002) أثناء `tools/netwatch.ps1` (SC-004).

> **البنود المعلَّمة (+خطة)** في `contracts/fr010-checklists.md` (RAD-F11/F12، QA-F06..F08، NMIS-F11/F12، ATP-F10/F11، JR-F07/F08) **معتمدة بالقرار 10** (2026-10-27) وتدخل `total_count`.

### Tests for User Story 2 ⚠️

- [ ] T089 [P] [US2] Write FR-010 harness `tests/e2e/test_fr010_checklists.py`: يقرأ المعرّفات من `contracts/fr010-checklists.md`، ويكتب FR010Run (`run_id`، `platform_id`، `at`، `snapshot_tree_sha256`، `checklist_version`، `passed_count`/`total_count`) وFR010Item (`result` ∈ {`pass`,`fail`,`blocked`}، `evidence_sha256` لصورة في مخزن البيت)؛ بند بلا صورة ⇒ ليس `pass`؛ `checklist_version` يشير إلى نسخة قائمة **معتمدة** فقط (النسخة 1 = بنود المواصفة + (+خطة) المعتمدة بالقرار 10)؛ النتيجة تُعرض في البيت (FR-028)
- [ ] T090 [P] [US2] Write `tools/netwatch.ps1` (R12): لقطات `Get-NetTCPConnection` لعمليات المنظومة (البيت، المنصات، Ollama، ATPAS) كل ثانية؛ أي عنوان غير loopback ⇒ سطر في السجل وفشل SC-004؛ يُشغَّل مع T089

### Implementation for User Story 2 — NMIS الكامل

- [ ] T091 [US2] (فريق الهندسة) Generate the fictional catalog for NMIS full (N8) في قاعدته الجديدة: منافسات وجهات وضمانات وفريق وتقييمات ومواعيد خيالية تغطي NMIS-F01..F09، بعد فحص الأسماء، مع `samples/synthetic/nmis/RIGHTS.md`
- [ ] T092 [US2] Verify NMIS-F01..F10 through T089 (F10 = مسار 001 US1، W2)؛ وNMIS-F11/F12
- [ ] T093 [US2] Disclose in the home maturity statement «كانبان NMIS ومهام الخيط غير مربوطين بعد» حتى T094 (R1، المبدأ X) في `platforms/nmis/noor_registry/maturity.json`
- [ ] T094 [US2] **بعد 2026-10-31 وقبل 2026-11-09**: Link accepted tenders to NMIS full kanban via `noor.tender/v1` (NMIS-N9، R1) مع اختبار مُنتِج ومستهلك؛ ثم إزالة إفصاح T093

### Implementation for User Story 2 — الرادار

- [ ] T095 [US2] Point radar at `NOOR_RADAR_DB` from T051 and show data age/source (RAD-07) in `platforms/radar/`
- [ ] T096 [US2] Verify RAD-F01..F10 through T089 (F10 = 001 US1، W1)؛ RAD-F11/F12

### Implementation for User Story 2 — JoUReady

- [ ] T097 [US2] Implement local compatibility shim `platforms/jouready/ui/jr-local-shim.js` (JR-D7): واجهة `db` فوق مسارات FastAPI محلية خلف الحارس، بلا `claude.use` ولا `EMBED_DATA` سحابي، ببيانات منافسة 001 المصطنعة فقط؛ إن لم تعمل قبل بوابة 2026-10-30 ⇒ JoUReady «لم تجتز شروط العرض» مع الإفصاح، وشاشات نتائج 001 في البيت لا تُحسب اجتيازًا
- [ ] T098 [US2] Verify JR-F01, F02, F04, F05, F06 through T089 (F04 ثلاثية الأدلة يُثبَّت تعريفها على اللقطة)؛ JR-F03 بعد T075؛ JR-F07/F08

### Implementation for User Story 2 — ATPAS

- [ ] T099 [US2] (فريق الهندسة) Write synthetic activities `samples/synthetic/atpas-activities/` (لا وكلاء، ATP-D7) مع نشاط «غير مصرَّح» لـ ATP-F05 و`RIGHTS.md`؛ ويُشار إليها من `NOOR_ATPAS_CONTENT_DIR`
- [ ] T100 [US2] Verify ATP-F01..F09 through T089 بصور يدوية موثّقة لنوافذ ATPAS (F08 CSV بلا عمود مسار، ATP-D8)؛ ATP-F10/F11 (وظيفة F10 نفسها مختبرة في T080)

### Implementation for User Story 2 — التحليل السريع

- [ ] T101 [US2] Implement the local job runner inside Express in `platforms/quick-analysis/mcp-server/noor-runner/` (بلا n8n): طابور في الذاكرة + ملف حالة في `NOOR_DATA_DIR/qa/`؛ QAJob بقيوده (`job_id` UUID «يُتحقق من صيغته قبل أي بناء مسار»؛ `level` ∈ {`quick`,`standard`,`deep`}؛ `state` ∈ {`uploaded`,`extracting`,`analyzing`,`rendering`,`done`,`failed`} «خطّية؛ أي فشل ⇒ `failed` برسالة، ولا تقرير جزئي يُعرض مكتملًا»)؛ استدعاء مولّد التقارير بعملية فرعية بقائمة وسائط؛ تصدير الحالة بعقد `noor.qa-analysis/v1` إلى البيت، ومستهلكه في البيت `platforms/nmis/noor_registry/views_qa_status.py` يتحقق بالمُتحقِّق ويرفض حقلًا زائدًا ومسارًا مطلقًا وإصدارًا غير معروف ويعرض الحالة في صفحة المنافسة، مع اختبار مُنتِج ومستهلك `platforms/nmis/tests/test_qa_status.py`؛ **اختبار صحة الاستخراج** `platforms/quick-analysis/test/noor-extract.test.mjs` على `samples/synthetic/qa-rfp-001/`: النص المستخرج يحوي القيم الرقمية والتواريخ في `expected_facts.json` حرفيًا بعد التطبيع، **قبل** أي استدعاء للنموذج (الحد الأدنى للاختبارات: صحة الاستخراج)
- [ ] T102 [US2] Implement local upload in `platforms/quick-analysis/` (tus داخل Express على `/files` إن عملت حزمته بلا اتصال خارجي، وإلا multipart محلي — يُتحقق على اللقطة) خلف الحارس وبحدود T083
- [ ] T103 [US2] Wire the local model via Ollama on `127.0.0.1:11434` only from `noor.provider-config/v1` (R5)؛ **النموذج قابل للتبديل** (القرار 6): الإعداد يختار أي نموذج مثبت في Ollama باسمه، ويُرفض اسم غير مثبت برسالة واضحة؛ تبديل النموذج يُبطل نتيجة R6 السابقة فتعود المنصة «غير مُقاس» حتى يُعاد T106، ولا يُعرض نموذج قبل إثبات ترخيصه التجاري (T136)؛ المستويات الثلاثة بالنموذج نفسه (طول السياق ومراحل التلخيص، يُتحقق على سير العمل المنسوخ)؛ لا يُكتب ترخيص في README قبل ثبوته
- [ ] T104 [US2] (فريق الهندسة) Write `samples/synthetic/qa-rfp-001/` (كراسة PDF مصطنعة 20–40 صفحة) و`expected_facts.json` (20 حقيقة مرجعية) و`RIGHTS.md` — لا وكلاء ولا مقتطف من منافسة حقيقية (QA-U5)
- [ ] T105 [US2] Implement the R6 evaluator `platforms/quick-analysis/eval/`: م1 = الحقائق الصحيحة ÷ 20 (مطابقة آلية للأرقام والتواريخ المطبّعة + مراجعة بشرية موثّقة للنصية)، م2 = أرقام وتواريخ التقرير غير الموجودة في نص الكراسة بعد التطبيع (حتمي)، م3 = الزمن؛ يكتب QAEvalResult (`m1_fact_recall`، `m2_invented_numbers`، `m3_seconds`، `threshold_version`، `passed`، `reproduce_cmd`)
- [ ] T106 [US2] Run R6 (العتبة م1 ≥ 80% وم2 = 0، القرار 6) على جهاز العرض = جهاز التطوير (القرار 7: i9-14900K، ذاكرة 32 غيغابايت، RTX 5070 Ti بذاكرة 16 غيغابايت، Ollama 0.40.11) for each candidate model من إعدادات `candidates/` (T129) and record QAEvalResult؛ لا يُعرض التحليل السريع عاملًا إن فشل م2؛ النتيجة تُعرض في البيت بتعريفها وعينتها وتاريخها وطريقة إعادة إنتاجها، أو «غير مُقاس» (FR-016، FR-029)
- [ ] T107 [US2] Verify QA-F01..F04 through T089
- [ ] T108 [US2] QA-F05 PDF (القرار 4؛ المولّد في النسخة الاحتياطية يحوّل إلى PDF بـ LibreOffice `soffice`، وهو غير مثبت على جهاز العرض — تثبيته ومراجعة رخصته قرار من م. يوسف إن لزم): تصدير PDF محلي إن أمكن بلا Word ولا خدمة خارجية (يُتحقق على المولّد)، وإلا البند «لم يجتز» والمنصة لا تُعرض عاملة؛ لا حذف للبند إلا بتحديث `spec.md` بقرار المالك
- [ ] T109 [US2] Verify QA-F06..F08 through T089 (الوصف «نظرة أولى عامة بلا دليل» FR-013، وشارة «محلي»، ونتيجة R6 أو «غير مُقاس» في البيت)

**Checkpoint**: لكل منصة مستلمة FR010Run مسجّل، وكل بند بنتيجته وصورته.

---

## Phase 5: User Story 3 — شكل ولغة واحدة (Priority: P1)

**Goal**: كل شاشة في الخمس بالشعار والاسم والألوان والخط نفسها، و«منافسة» لا «مناقصة»، والحالات بعرض واحد منفصل.

**Independent Test**: صور أسطح FR-030 جنبًا إلى جنب + فحص آلي للأسماء الممنوعة والمصطلحات والتباين (quickstart §7).

### Tests for User Story 3 ⚠️

- [ ] T110 [P] [US3] Write surface capture tool `tools/surfaces/capture.py` (Playwright بمتصفح مثبت محليًا، بلا تنزيل وقت الاختبار): لكل سطح ويب في الوضعين صورة + نص الصفحة المستخرج + تقرير تباين من الأنماط الفعلية؛ ويرفض العمل إن احتاج تنزيلًا
- [ ] T111 [P] [US3] Write checks `tools/surfaces/check.py`: SC-005 (صفر اسم ممنوع في النص والبيانات الوصفية لنطاق FR-025)، SC-006 (الشعار والاسم والخط ولون الوضع 100%)، SC-007 (صفر «مناقصة» خارج الاقتباس الحرفي)، SC-008 (كل زوج ≥4.5:1 والنص الكبير ≥3:1 والشارات)
- [ ] T112 [P] [US3] Write label-rendering tests `platforms/nmis/tests/test_labels_render.py`: «مطابق» + «مقترح» يظهران بشارتين منفصلتين بالنص والشكل واللون والتسمية المسموعة (US3-2، FR-024)، ولا تمييز باللون وحده؛ تنقل بلوحة المفاتيح ومؤشر تركيز ظاهر؛ RTL مع حفظ اتجاه LTR

### Implementation for User Story 3

- [ ] T113 [US3] Apply `noor-tokens.css` and `labels.ar.json` to the home shell and 001 pages in `platforms/nmis/noor_registry/templates/` (أسطح S-HOME-01..07 المثبتة)، لاجتياز T112
- [ ] T114 [P] [US3] NMIS full: `company_profile` و`features` من ملف التعريف، ومظهر `noor` يقرأ الرموز في `platforms/nmis/full/`
- [ ] T115 [P] [US3] Radar UI reads `noor-tokens.css` at runtime in `platforms/radar/` (لا نسخ مضمَّنة)
- [ ] T116 [P] [US3] Quick-analysis header and Word/PDF report styles from the tokens in `platforms/quick-analysis/`
- [ ] T117 [P] [US3] ATPAS `company_profile.json` و`theme.py` يقرآن `noor_tokens.json` (فاتح فقط) وأيقونة البناء في `platforms/atpas/`
- [ ] T118 [P] [US3] JoUReady local template uses the tokens and the two separate badges (JR-D7، FR-023) in `platforms/jouready/ui/`
- [ ] T119 [US3] Replace visible «مناقصة» with «منافسة» in every received platform's UI strings and outputs (عدا الاقتباس الحرفي)، مع اختبار SC-007 لكل منصة
- [ ] T120 [US3] (القرار 10أ: يوم دخول لقطة كل منصة) Pin each platform's surface catalog in `specs/002-full-noor-suite/contracts/surfaces.md` بأسماء الشاشات الحقيقية ومساراتها، وربط كل بند FR-010 وكل قيمة حالة بسطح ولقطة وتقرير تباين، ثم تعديل موثّق في `plan.md`؛ لا تُقيَّم `demo_gate` للمنصة قبل اعتماد كتالوجها
- [ ] T121 [US3] Run T110–T111 on all pinned surfaces + outputs S-OUT-01..06 (غلاف Word وصفحة محتوى وصفحة فيها إنجليزية من ATPAS، وغلاف تقرير التحليل السريع، وتقرير JoUReady، والبيانات الوصفية)، وسجّل النتيجة في «سجل البوابات»
- [ ] T122 [US3] Produce the 2026-10-29 images **بعد توحيد الشكل واللون في الخمس كلها** (القرار 11-د) ثم إعادة اللقطات بعد T113–T118؛ إن لم تكتمل الخمس في موعد الصور يُسجَّل في «سجل البوابات» أن الشرط لم يتحقق ويُطلب من م. يوسف قرار صور معدَّل، ولا تُحسب صور جزئية إنجازًا

**Checkpoint**: الأسطح المثبتة تجتاز SC-005..SC-008.

---

## Phase 6: User Story 4 — هوية من الإعداد (Priority: P2)

**Goal**: تبديل ملف تعريف الهوية يغيّر المنصات الخمس ومخرجاتها دون تعديل كود.

**Independent Test**: تشغيل بملف تعريف مصطنع والتحقق من الأسطح والمخرجات (SC-009).

- [ ] T123 [P] [US4] Write synthetic test profile `packages/noor_identity/tests/fixtures/synthetic_profile/` (اسم وهمي ولوحة مختلفة، شعار نصي)
- [ ] T124 [US4] Write failing test `tests/e2e/test_identity_swap.py`: بتوجيه `NOOR_IDENTITY_DIR` إلى T123 تظهر الهوية الوهمية في كل منصة مستلمة ومخرجاتها ولا يبقى «النور» (US4-1)؛ ملف ناقص أو تالف ⇒ كل منصة تفشل في البدء برسالة واضحة (US4-2)
- [ ] T125 [US4] Add the identity loader with fail-fast to every received platform (البيت، NMIS الكامل، الرادار، التحليل السريع، ATPAS، JoUReady)، تقرأ `NOOR_IDENTITY_DIR/build/` وقت التشغيل فقط، لاجتياز T124

---

## Phase 7: User Story 5 — مزود الذكاء الاصطناعي بقرار العميل (Priority: P2)

**Goal**: المحلي افتراضي ظاهر؛ السحابي مرفوض في نسخة الهاكاثون؛ منصة واحدة كحد أقصى بموافقة موقّعة في نسخة عميل.

**Independent Test**: تشغيل افتراضي مع netwatch (صفر اتصال خارجي)، ومحاولة تفعيل السحابي (تُرفض) (US5-1/2).

- [ ] T126 [P] [US5] Write failing loader tests `packages/noor_runtime/tests/test_provider_config.py` و`provider_config.test.mjs`: `mode: local` و`endpoint` loopback فقط؛ بناء الهاكاثون يرفض `cloud` **قبل** قراءة `consent`؛ أكثر من منصة `cloud` ⇒ فشل البدء في البيت؛ فشل المحلي ⇒ «تعذّر التشغيل المحلي» بلا تحوّل؛ US5-3 بمحوّل مزود وهمي على loopback في اختبار وحدة فقط مع تحقق `signature_ed25519` على تسلسل قانوني للحقول (`provider`، `data_sent`، `processing_location`، `retention`، `signer`، `signed_on`)
- [ ] T127 [US5] Implement `packages/noor_runtime/noor_runtime/provider_config.py` و`provider_config.mjs`، لاجتياز T126؛ لا يُبنى مسار السحابي أبعد من المُحمِّل والرفض والاختبار (R8)
- [ ] T128 [US5] Wire the loader into quick-analysis, radar agents and JoUReady providers، وكشف `provider_mode` في سجل المنصات ورأس كل منصة وشارة «محلي» قبل الرفع في التحليل السريع (US5-1)
- [ ] T129 [US5] Write `NOOR_PROVIDER_CONFIG_DIR/` default files (`mode: local`، `endpoint` loopback) for the three platforms — **إعداد مرشَّح** صالح للمخطط في `NOOR_PROVIDER_CONFIG_DIR/candidates/` لكل نموذج مثبت ثبت ترخيصه (T136)، يقرؤه المقيّم في T106 فقط ولا يقرؤه البناء المعروض؛ يُرقّى إلى الملف الافتراضي بعد اجتياز R6 (القرار 6)، والمرشَّح الفاشل لا يُرقّى ولا يدخل بوابة العرض؛ وبلا ملف افتراضي يفشل بدء المنصة برسالة «تعذّر التشغيل المحلي»، وتأكيد أن NMIS وATPAS `provider_mode = none`

---

## Phase 8: User Story 6 — وضع داكن (Priority: P3)

**Goal**: المنصات الويب تتبع وضع النظام ويمكن تثبيته من البيت؛ ATPAS والمخرجات فاتحة.

**Independent Test**: فتح كل منصة ويب بالوضع الداكن واجتياز التباين (US6-1).

- [ ] T130 [P] [US6] Write failing test `tests/e2e/test_dark_mode.py`: `prefers-color-scheme: dark` ⇒ لوحة الوضع الداكن في كل منصة ويب مستلمة؛ التثبيت اليدوي من البيت يُحفظ في `theme_pref` ويُمرَّر في التأكيد (`theme` في `noor.principal/v1`) ويتغلب على النظام؛ ATPAS والمخرجات فاتحة دائمًا (FR-022)
- [ ] T131 [US6] Implement theme pinning in the home (`platforms/nmis/noor_registry/views_shell.py`) والاستجابة لـ `theme` في المنصات الويب، لاجتياز T130، ثم إعادة T121 بالوضع الداكن

---

## Phase 9: Polish & Cross-Cutting Concerns

- [ ] T132 Checkpoint **2026-10-28 مساءً** (م. يوسف، FR-031): كل منصة لم تُغلق تعرضاتها أو لم تدخل لقطتها ⇒ `demo_gate = at_risk` بقرار مسجّل (Approval `demo_gate_decision`)؛ السجل في «سجل البوابات»
- [ ] T133 Demo-gate decision **2026-10-30 مساءً** (م. يوسف، FR-031، R13): لكل منصة `passed` فقط إن اجتازت FR-003 (T088) وFR-006 (دليل الإغلاق) وكل بنود قائمتها المعتمدة في FR-010 بلا `fail` ولا `blocked`، واعتُمد كتالوج أسطحها (T120)، واجتازت ISO-REAL (T087)؛ وإلا «لم تجتز شروط العرض» مع الإفصاح. **الأمان لا يُتنازل عنه لأجل الموعد**
- [ ] T134 Disclosures in the home (FR-028، SC-011) in `platforms/nmis/noor_registry/maturity.json` و`templates/shell/`: إفصاحات 001 FR-020 + وضع المزود لكل منصة + نتيجة FR-010 + كل منصة لم تجتز + وعد البيانات المعدّل (المبدأ V) + نموذج التهديد المعلن (`noor.localhost` لا يُستعمل لغير المنظومة)؛ ولا «جاهز للبيع» قبل إثبات FR-027
- [ ] T135 **2026-10-31** (م. يوسف يجهّز ويعتمد؛ م. عبدالله يرفع من حسابه): رفع ملف العرض الأولي والنماذج بما اجتاز مع الإفصاح؛ اختبار كل رابط وصورة، وصورة شاشة للرفع الناجح
- [ ] T136 [P] Vision 2030 / licensing verifications (حدّث جدول المراجع في `specs/002-full-noor-suite/plan.md`): ترخيص كل نموذج محلي يُختار، من صفحة نشره الرسمية (2026-10-29 للأول، وعند كل تبديل) · حقوق الشعار (إقرار م. يوسف) وTajawal (OFL 1.1) في `config/identity/noor/RIGHTS.md` · PDPL قبل تهيئة حساب «معتمِد المراجعة» (= 001 T073) · NDMO وNCA ومبادئ SDAIA 2026-11-05 (= 001 T097). لا يُدّعى امتثال قبل المصدر الرسمي المؤرَّخ
- [ ] T137 Run 001 regression `pytest packages/noor_contracts platforms/nmis/tests tools/tests` (SC-010) بعد كل تغيير في نواة البيت، وسجّل النتيجة
- [ ] T138 Run `tools/scan_public_repo.py --diff --require-blocklist` وفحص التاريخ قبل كل commit (SC-005، = 001 T099)
- [ ] T139 Update `README.md` بنضج كل منصة الفعلي ووعد البيانات المعدّل، وكل رقم بتعريفه وعينته وتاريخه وطريقته أو «غير مُقاس» (المبدأ X)
- [ ] T140 Finalize the real commands in `specs/002-full-noor-suite/quickstart.md` (§1–§9) وشغّلها كلها
- [ ] T141 `/speckit.analyze` ثم `/speckit.implement` ثم `/speckit.converge` حتى **Converged** لكل معيار قبول، وتحديث علامات هذا الملف
- [ ] T142 Freeze **2026-11-09** = **001 T103** (آخر موعد لاكتمال الخمس)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)**: يبدأ فورًا.
- **Foundational (2)**: (أ)–(و) بعد Setup وتحجب كل القصص. (ز) لكل منصة مستقلة عن غيرها؛ كل استيراد ينتظر بوابة تعرضه وقرار 8.
- **US1 (3)**: بعد (أ)–(و). لكل منصة: NMIS الكامل بعد T046؛ الرادار بعد T050؛ JoUReady **في التجهيز** بعد T054، وT055 (الاستيراد) ينتظر T072–T076؛ ATPAS بعد T058؛ التحليل السريع **في التجهيز** بعد T060، وT062 ينتظر T082–T085. T087 (ISO-REAL) لكل منصة بعد تشغيلها خلف الوكيل.
- **US2 (4)**: لكل منصة بعد مهامها في US1 (لا وظيفة تُعرض بلا حارس). T094 بعد 2026-10-31. T106 يحتاج الجزء المرشَّح من T129 (US5) وT127 قبله، فيُنفَّذان مبكرًا لهذا الغرض.
- **US3 (5)**: T110–T113 بعد (و)؛ مهام كل منصة بعد استلامها؛ T120 يوم دخول كل لقطة.
- **US4 (6)**: بعد T125 لكل منصة مستلمة.
- **US5 (7)**: T126–T127 بعد (هـ)؛ T128 بعد استلام المنصات الثلاث المعنية.
- **US6 (8)**: بعد US3.
- **Polish (9)**: T132 في 2026-10-28، T133 في 2026-10-30، T135 في 2026-10-31، T142 في 2026-11-09؛ الباقي بعد القصص.

### الترتيب الزمني المتوقع (R13 — معتمد بالقرار 9، 2026-10-27)

الأساس ⇐ NMIS ⇐ الرادار ⇐ JoUReady ⇐ ATPAS ⇐ التحليل السريع. التوقع الصادق: 2–3 منصات تجتاز في 2026-10-30، والباقي «لم تجتز شروط العرض» مع الإفصاح ويكتمل قبل 2026-11-09، متداخلًا مع W1–W5 في 001 (لا تتغير).

### Parallel Opportunities

- المرحلة 1: T002–T004 معًا.
- المرحلة 2: T007–T009 معًا؛ اختبارات T011 وT014 وT015 وT017 وT019 وT021 وT023 وT025 وT027 وT029 وT031 وT035 وT037 وT039 معًا (ملفات مختلفة)؛ تجهيز المنصات (T045، T049، T054، T057، T060) بالتوازي بعد T038.
- US3: T114–T118 معًا بعد T113 واستلام كل منصة.
- فريق الهندسة: T051 وT095 وT103 وT108 بالتوازي مع مسارات الكود (ملفات مختلفة).

## Parallel Example: User Story 1

```text
Task: "T063 E2E test tests/e2e/test_suite_sso.py"
Task: "T064 Cross-origin test tests/e2e/test_suite_isolation.py"
Task: "T065 Route-enumeration contract tests/support/route_enum.py"
Task: "T078 Home-side desktop tests platforms/nmis/tests/test_desktop_sso.py"
```

## Implementation Strategy

> الترتيب معتمد (القرار 9). عدد المنصات المتوقع اجتيازها في 2026-10-30 توقع لا التزام؛ ما لا يجتاز يُفصح عنه (T134).

### MVP أولًا (الأساس + US1 على NMIS الكامل والرادار)

1. المرحلتان 1 و2 (مع بوابة 2026-10-28).
2. US1 لـ NMIS الكامل والرادار + T087 لهما.
3. US2 لهما + US3 لأسطح البيت ولهما.
4. **توقف وتحقق** قبل 2026-10-30: منصتان عاملتان من دخول واحد بإفصاح صادق عن البقية.

### التسليم التدريجي

JoUReady ثم ATPAS ثم التحليل السريع، كلٌّ يُضاف عند اجتياز بوابته أو يبقى «لم تجتز شروط العرض» مُفصَحًا عنه، ويكتمل الباقي قبل التجميد 2026-11-09.

## التنفيذ بأدوات خارجية (المبدأ V، plan.md «أدوات التطوير»، R14)

- **MiniMax** (`minimax/minimax-m3.1-flash` عبر OpenRouter، جهد `xhigh`، المفتاح من `OPENROUTER_API_KEY`): **مسموح** للكود الجديد الصغير بملفات المهمة المسماة فقط: T008–T011 (أجزاء الاختبارات والمُتحقِّق)، T023–T028، T031–T032، T037–T040، T089، T110–T111، T126–T127.
- **حدّ Claude (X1، الخيار أ، 2026-10-27؛ مشدَّد بعد N2)**: في مجلد التجهيز أوامر آلية فقط، ولا يرى إلا الملخص المعتم (أعداد ومعرّفات بصمة، بلا أسماء ولا مسارات ولا أسطر ولا نص)؛ التفاصيل في `NOOR_PRIVATE_REPORTS_DIR` لـ م. يوسف؛ الكود يُفتح ملفًا ملفًا بعد الفحص ووروده في قائمة «منقّح» يعتمدها م. يوسف؛ الـ prompts وتصدير السير ومولّد التقارير والقوالب بعد مراجعة م. يوسف فقط (plan.md «أدوات التطوير»).
- **ممنوع على MiniMax وCodex**: أي محتوى من مجلد التجهيز (T045، T049، T054، T057، T059–T061، ومهام US1 التي تعمل في التجهيز: T072–T074، T082–T084) قبل دخوله المستودع بالبصمة؛ والـ prompts وسير العمل ومولّد التقارير المنسوخة من السيرفر قبل فحصها؛ ومحتوى `samples/synthetic/` الفني (T051 الأسماء، T091، T099، T104)؛ والأسرار والمفاتيح.
- **نواة الجلسة والوكيل** (T013، T016، T018، T020، T022، T079): يكتبها Claude ويراجعها Codex (قراءة فقط) لأنها تغيّر حدود الثقة (المبدأ XI).
- **قبل كل إرسال**: `tools/scan_public_repo.py --paths` على الملفات المرسلة، والتسجيل في «سجل الإرسال» أدناه.

### سجل الإرسال إلى MiniMax

| التاريخ | المهمة | الملفات المرسلة | نتيجة الفحص قبل الإرسال | مراجعة Claude |
|---|---|---|---|---|
| — | — | — | — | — |

## سجل البوابات والقرارات

> لا تفاصيل تعرض حساسة ولا أسماء أشخاص حقيقيين هنا (المستودع عام). الدليل الكامل خارج المستودع.

| المهمة | البند | الموعد | المالك | النتيجة | التاريخ |
|---|---|---|---|---|---|
| — | القرار 1 (R1) | 2026-10-28 | م. يوسف | **معتمد** | 2026-10-27 |
| — | القرار 2 (R2) + تجربة العزل على محاكاة | 2026-10-28 | م. يوسف | **معتمد تصميمًا**؛ التجربة اجتازت على محاكاة بملاحظة ملزمة (فحص `Origin`)؛ ISO-REAL مفتوحة لكل منصة (T087) | 2026-10-27 |
| T006 | القرار 3: التحليل السريع بلا n8n (R7) | 2026-10-28 | م. يوسف | **معتمد**: «نقل منطق السير إلى منفّذ محلي داخل Express» | 2026-10-27 |
| T006 | القرار 4: PDF في التحليل السريع | عند دخول اللقطة | م. يوسف | **معتمد**: «تصدير محلي إن أمكن، وإلا يُسجَّل البند «لم يجتز» ولا تُعرض المنصة عاملة» | 2026-10-27 |
| T006 | القرار 5: إعادة بناء مولّد التقارير إن تعذّر SSH | 2026-10-28 مساءً | م. يوسف | **لا إعادة بناء**: الوصول إلى السيرفر متاح، وتوجد نسخة محلية على جهاز م. يوسف (مسارها يُبلَّغ) | 2026-10-27 |
| T006 | القرار 6: النموذج المحلي ومعياره وحقه التجاري | 2026-10-29 | م. يوسف | **معتمد** (م1 ≥ 80%، م2 = 0، الحق التجاري مثبت) **مع مرونة**: اختيار أي نموذج مثبت في Ollama مستقبلًا بالإعداد | 2026-10-27 |
| T006 | القرار 7: مواصفات جهاز العرض | 2026-10-29 | م. يوسف | **قُرئت من الجهاز بإذنه**: i9-14900K (24 نواة)، 32 غيغابايت، RTX 5070 Ti 16 غيغابايت، Windows 11 Pro، Ollama 0.40.11 | 2026-10-27 |
| T006 | القرار 8: صيغة `SOURCE.md` | قبل أول لقطة | م. يوسف | **معتمد**: وسم بديل، والمرجع عند المالك | 2026-10-27 |
| T006 | القرار 9: الترتيب والتوقع | 2026-10-28 | م. يوسف | **أجاب عن شكل البيت**: «المنصة الأم وبها خمسة أزرار للخمس منصات، وقابلة للتطوير والتحسين مستقبلًا»؛ ثم **اعتمد الترتيب**: «الأساس ثم NMIS ثم الرادار ثم JoUReady ثم ATPAS ثم التحليل السريع، مع الإفصاح عمّا لا يجتاز في 30 أكتوبر» | 2026-10-27 |
| T006 | القرار 10: قوائم FR-010 بإضافات الخطة | 2026-10-28 | م. يوسف | **معتمد** | 2026-10-27 |
| T006 | القرار 10أ: كتالوج أسطح كل منصة | يوم دخول كل لقطة | م. يوسف | **معتمد** (يُثبَّت ويُعتمد يوم دخول كل لقطة) | 2026-10-27 |
| T006 | القرار 11: الشعار وTajawal، قائمة الهويات النهائية، مكان مفتاح SSH، صورة 29 أكتوبر | 2026-10-29 | م. يوسف | (أ) **اعتمد** حق الشعار وTajawal؛ (ب) القائمة النهائية: أسماء الهوية السابقة (العربية واللاتينية)، وكل موضع يُستبدل بـ«النور»؛ (ج) إعداد SSH قائم على جهاز التطوير؛ (د) **توحيد الشكل واللون في الخمس ثم إعادة اللقطات** | 2026-10-27 |
| G1 | اعتماد م. يوسف لنطاق خطة 002 للتنفيذ (المبدأ XI) — بعد إصلاحات `/speckit.analyze` وقبل `/speckit.implement` | قبل التنفيذ | م. يوسف | **أمر بالتنفيذ**: «نفذ انت عبر كوديكس … اريد وواجب الان ان نصل للشكل العام للمنصه». بدأ التنفيذ بشريحة البيت (T007، T029–T036 جزئيًا) على كود جديد وبيانات مصطنعة فقط؛ ملاحظة R1 (حدّ مجلد التجهيز) باقية ولا تمس هذه الشريحة، ولا يُلمس التجهيز ولا السيرفر قبل حسمها | 2026-10-27 |
| R1 (`/speckit.analyze` ج3) | من يشغّل أوامر النسخ والفحص في مجلد التجهيز (حدّ Claude) | قبل أي لقطة | م. يوسف | **معتمد**: «أنا أشغّلها بسكربتات تكتبها، وأعطيك الملخص المعتم فقط» — Claude يكتب الأدوات والسكربتات في المستودع ويختبرها على بيانات مصطنعة، ولا يشغّل شيئًا في `NOOR_STAGING_DIR` ولا على السيرفر | 2026-10-27 |
| T044 | `EXP-NMIS-PASSWORDS` | 2026-10-28 مساءً | م. يوسف | = 001 T007 | — |
| T047 | خط أساس اختبارات NMIS الكامل | — | م. يوسف | — | — |
| T048 | RAD-02 | 2026-10-28 مساءً | م. يوسف | = 001 T008 | — |
| T052 | إذن قراءة مستودع JoUReady | — | م. يوسف | — | — |
| T053 | `EXP-JR-TEMPLATE` | 2026-10-30 | م. يوسف | = 001 T071 | — |
| T056 | `EXP-ATPAS-LICENSE` | 2026-10-30 | م. يوسف | = 001 T055 | — |
| T059 | الوصول إلى سيرفر التحليل السريع (QA-U8) | 2026-10-28 مساءً | م. يوسف | — | — |
| T076 | `EXP-JR-AUTH` | 2026-10-30 | م. يوسف | — | — |
| T085 | `EXP-QA-ROUTES-TUS` | 2026-10-30 | م. يوسف | — | — |
| T087 | ISO-REAL: NMIS الكامل / الرادار / JoUReady / التحليل السريع | قبل T133 | م. يوسف | — | — |
| T132 | نقطة فحص FR-031 | 2026-10-28 مساءً | م. يوسف | — | — |
| T133 | بوابة العرض لكل منصة | 2026-10-30 مساءً | م. يوسف | — | — |
| T135 | الرفع الأولي | 2026-10-31 | م. يوسف / م. عبدالله (رفع) | — | — |
| T142 | التجميد | 2026-11-09 | م. يوسف | = 001 T103 | — |

## Notes

- [P] = ملفات مختلفة بلا اعتماد. كل مهمة لقطة لا تبدأ قبل بوابتها، مهما كان التوازي ممكنًا.
- لا commit ولا push إلا بطلب صريح؛ وقبل أي commit: T138.
- أي تغيير في المتطلبات أثناء التنفيذ: spec.md ثم plan.md ثم هذا الملف ثم الكود (المبدأ XI).
- لم يُكتب أي كود ولم يُشغَّل أي اختبار عند إنشاء هذا الملف (2026-10-27).
