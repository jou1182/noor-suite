# Data Model: الخيط الواحد على منافسة مصطنعة

**Plan**: [plan.md](plan.md) · المالك: NMIS يملك كل الكيانات أدناه ما عدا ما يُذكر. العقود بين المنصات في [contracts/](contracts/).

قواعد عامة: لا حقل يحمل مسارًا محليًا أو معرّف جلسة أو سرًا (المبدأ VI). كل وقت بتوقيت ISO 8601 مع المنطقة. كل كيان يحمل `synthetic: true` في نسخة الهاكاثون.

## TenderRecord — سجل المنافسة (SYS-13)

| الحقل | النوع | القاعدة |
|---|---|---|
| `tender_id` | نص `NT-YYYY-NNNN` | يصدره NMIS وحده، فريد، لا يتغير |
| `title` | نص | إلزامي |
| `issuing_entity` | نص | الجهة الطارحة المصطنعة، إلزامي |
| `closing_at` | وقت | إلزامي للاعتماد؛ قد يصل ناقصًا (حالة «ناقص») |
| `project_type` | نص | من قائمة أنواع ATPAS، إلزامي قبل البناء؛ لا يرد في عقد الرادار، ويُستكمل في NMIS بقرار `field_completion` |
| `activity_codes` | قائمة رموز أنشطة | تُختار وتُحفظ في NMIS؛ يلزم عنصر واحد على الأقل قبل إصدار `noor.tender/v1` |
| `status` | `candidate` · `accepted` · `rejected` | انظر الانتقالات |
| `source_name` / `source_ref` | نص / نص | إلزاميان للوارد من الرادار؛ فريدان معًا؛ فارغان للإدخال اليدوي |
| `etimad_ref` | نص اختياري | معلومة إضافية |
| `source_updated_at` | وقت | من الرادار؛ يُعرض عمر البيانات |
| `missing_fields` | قائمة | حقول **قبول المنافسة** الناقصة فقط؛ تمنع القبول حتى استكمالها بقرار مسجّل. `project_type` و`activity_codes` مطلوبان قبل البناء، لا قبل القبول. |
| `synthetic` | منطقي | يجب `true` |

**الانتقالات**: `candidate → accepted` (اعتماد بصلاحية + لا حقول ناقصة) · `candidate → rejected` (قرار بصلاحية). لا انتقال عكسي في العرض. أي انتقال ينشئ `Approval`.

**منع التكرار**: قيد فريد (`source_name`, `source_ref`). الوارد المكرر يحدّث `title`/`closing_at`/`source_updated_at` فقط ويسجل `ChangeLog`.

## User — الحساب المصطنع (R6)

`user_id` · `display_name` · `kind` ∈ {`proposal_manager`, `review_approver`, `member`, `viewer`} · `shared` = `false` دائمًا · `synthetic` = `true` · `operator_label` (لـ `review_approver` فقط: المشغّل البشري المحدد، يُدخل في القاعدة المحلية عند الإعداد ولا يُكتب في المستودع). حساب `viewer` منفصل عن `review_approver` ولا يُمنح أي صلاحية اعتماد. `kind` وصف للحساب، ولا يحدد صلاحياته؛ مصدر الصلاحية هو `Membership`. يجب أن يكون `operator_label` غير فارغ قبل تفعيل صلاحية `review_approver`. `enabled` = `false` لحساب `review_approver` عند الإنشاء، ويُرفض دخوله حتى تسجيل الإذن والمشغّل ومدة الاحتفاظ والمنح.

## Membership — الصلاحية على المنافسة (R6، JR-D0 المعدّل)

`user_id` · `tender_id` · `role` · `owner_authorization_ref` · `configured_by_user_id` · `granted_at` · `grant_approval_id`. يُوثَّق إذن م. يوسف الصريح، بصفته مالك JoUReady، بمنح صلاحية المراجعة لهذه المنافسة، ثم يسجّلها في NMIS عبر إجراء تهيئة محلي موثّق الهوية؛ يسجّل قرار `permission_grant` الإذن ومن نفّذ التهيئة ووقتها. لا يمنح الحساب الصلاحية لنفسه، ولا تُمنح لحساب `viewer`. يجوز جمع `approver` و`review_approver` للحساب نفسه بمنحين منفصلين.

- `role` ∈ {`approver`, `review_approver`, `member`, `viewer`}؛ للحساب الواحد أكثر من صف على المنافسة نفسها (فريد: `user_id` + `tender_id` + `role`).
- `approver`: قبول المنافسة، واعتماد إنشاء المهام من الثغرات.
- `review_approver`: اعتماد `ReviewReport` و`Finding` فقط.
- حساب العرض `viewer` على كل شيء ولا يغيّر شيئًا.
- عند إنشاء منافسة (استيراد أو إدخال يدوي) يُنشأ صف `approver` للمنشئ في المعاملة نفسها، مع Approval `permission_grant` يحمل مرجع تخويل الإنشاء.

## CreationGrant — تخويل إنشاء المنافسات المصطنعة (FR-002a، U1)

`user_id` · `capability` = `create_synthetic_tender` · `owner_authorization_ref` (إذن م. يوسف الموثّق) · `configured_by_user_id` · `granted_at` · `grant_approval_id`. يُسجَّل عبر إجراء التهيئة المحلي وقرار `permission_grant`. لا يُستنتج من `kind`، ولا يُمنح لحساب `viewer`، ولا يمنحه الحساب لنفسه. نطاقه نسخة العرض والمنافسات المصطنعة فقط. لا يمنح قبول المنافسة؛ القبول قرار `tender` منفصل.

## Approval — قرار الاعتماد (المبدأ I)

| الحقل | القاعدة |
|---|---|
| `approval_id` | فريد |
| `subject_type` | `tender` · `report` · `finding` · `gap_task` · `manual_entry` · `field_completion` · `import` · `permission_grant` |
| `acting_role` | الدور الذي اتُّخذ به القرار (`approver` أو `review_approver` …)؛ `report` و`finding` يتطلبان `review_approver` على المنافسة نفسها |
| `subject_id` | معرّف الموضوع |
| `decision` | `approved` · `approved_with_reservation` · `rejected` |
| `reservations` | نص، إلزامي مع «تحفظ» |
| `actor_user_id` · `decided_at` | من الجلسة الموثقة، لا من الطلب |

لا يُنشأ إلا عبر دالة التفويض. غير قابل للتعديل (يُضاف قرار جديد).

## Task — مهمة

`task_id` · `tender_id` · `title` · `owner_user_id` · `due_at` · `status` (`open`/`done`) · `origin` (`template:<id>` أو `gap:<finding_key>`) · `proposal_version` (للمهام من ثغرة). المهام من القالب تُنشأ عند `accepted` فقط.

## ProposalVersion — إصدار العرض (FR-010، ATP-D8)

`tender_id` · `version` (1، 2، …) · `sha256` · `built_at` · `requested_by` · `activity_codes` · `rejected_activities[{code, reason}]` · `status` (`built`/`failed`). الملف في مخزن NMIS باسم بصمته؛ لا مسار في الكيان. إعادة البناء ⇐ إصدار جديد؛ التقارير السابقة تبقى مربوطة بإصدارها.

## ReviewReport — تقرير المراجعة (FR-012..017)

`report_id` · `tender_id` · `proposal_version` · `proposal_sha256` · `rfp_sha256` · `report_sha256` (بعد الكتابة، في الختم) · `checks_run` · `limitations` · `approval_state` (`proposed`/`approved`/`approved_with_reservation`/`rejected`). يُنشأ `proposed` دائمًا، ولا يتغير إلا بقرار من صاحب `review_approver` على المنافسة (JR-D0 المعدّل).

## Finding — حكم

`finding_key` = SHA-256 لـ (`tender_id`, `criterion_id`, `evidence_locator`) — هوية التكرار (FR-019) · `criterion_id` · `result` (`match`/`mismatch`/`unverifiable`) · `sources[]` {`doc`: `rfp`/`proposal`, `sha256`, `locator`, `quote`} — لكل مصدر بصمته وموضعه واقتباسه الحرفي المستقل (إلزامي مع `match`، ≤300 حرف، يُتحقق منه في الملف ذي البصمة نفسها)؛ حكم فحص SBC يحمل مصدرًا من الكراسة وآخر من العرض · `approval_state`.

## Seal — ملف الختم (FR-016)

`report_id` · `algorithm` = `sha256` · `entries[{role, sha256, size, version_id}]` — إدخال واحد لكل دور بالترتيب `rfp` ثم `proposal` ثم `report`، تُرفض الأدوار المكررة أو الناقصة · `created_at`. التحقق: إعادة الحساب والمقارنة؛ أي اختلاف ⇐ فشل ظاهر.

## GapProposal — مقترح ثغرة (FR-018/019)

ينتجه JoUReady بحالة `pending` مع التقرير، ويستورده NMIS.

`finding_key` · `tender_id` · `report_id` · `proposal_version` · `summary` · `state` (`pending` → `finding_approved` → `task_created` · أو `rejected`). الانتقال إلى `task_created` يتطلب اعتمادين مسجلين (الحكم أو التقرير من `review_approver`، ثم إنشاء المهمة من `approver`). إن وُجدت مهمة بالمفتاح نفسه، تُربط بالتقرير الجديد بدل إنشاء ثانية.

## MaturityEntry — بيان النضج (FR-020)

`component` (منصة أو وصلة W1–W5) · `level` (L0–L3) · `state` (`working`/`dropped_manual`) · `disclosure` · `decided_at` (قرار الإسقاط، SC-008). تُضاف قائمة «ما لم يُنفَّذ» ثابتة من الإعداد: XER، مونت كارلو، التحليل السريع، حكم النموذج المحلي، المطابقة الهندسية الكاملة، التطور 3←5 وحالة تأكيد المرشدين.

## ChangeLog

`tender_id` · `field` · `old` · `new` · `source` (`radar_import`/`manual`) · `actor_user_id` · `at`.
