# عقود الخيط الواحد (`noor.*/v1`)

مخططات JSON Schema (draft 2020-12). كل مخطط يرفض الحقول غير المعرّفة (`additionalProperties: false`) ويشترط `synthetic: true` في نسخة الهاكاثون. فُحصت المخططات بـ `jsonschema` وبعينات صغيرة (2026-10-24).

| العقد | المُنتِج ← المستهلك | الوصلة | المتطلبات |
|---|---|---|---|
| [tender-candidate](tender-candidate.schema.json) | الرادار ← NMIS | W1 | FR-001..003، SYS-13، RAD-05 |
| [tender](tender.schema.json) | NMIS ← ATPAS، JoUReady | W3، W4 | FR-004، FR-008، ATP-D8، JR-D8 |
| [proposal-version](proposal-version.schema.json) | ATPAS ← NMIS | W3 | FR-010، FR-011، ATP-D8 |
| [review-report](review-report.schema.json) | JoUReady ← NMIS | W4 | FR-012..015، FR-017 |
| [seal](seal.schema.json) | JoUReady ← NMIS | W4 | FR-016، SC-004 |
| [gap-proposal](gap-proposal.schema.json) | JoUReady ← NMIS | W5 | FR-018، FR-019 |

## قواعد يفرضها المُتحقِّق فوق المخطط (`packages/noor_contracts/validate.py`)

المخطط وحده لا يمنع نصًا حرًا يحمل مسارًا، فيضيف المُتحقِّق:

1. رفض أي قيمة نصية تشبه مسارًا مطلقًا (`^[A-Za-z]:[\\/]`، `^\\\\`، `^/(home|Users|mnt|var|tmp)/`، `file://`) أو تحمل `session`/`sid=`/`token`. <!-- scan:allow=path.file_uri -->
2. حد حجم الملف (1 ميغابايت للعقد).
3. ترميز UTF-8 فقط.
4. يحمل كل مصدر في حكم فحص SBC بصمته وموضعه واقتباسه الحرفي المستقل، ويُتحقق من الاقتباس في الملف ذي البصمة نفسها. ويجب أن يحتوي الختم إدخالًا واحدًا لكل دور: `rfp` و`proposal` و`report`؛ تُرفض الأدوار المكررة أو الناقصة.
5. لحكم `match`، يُتحقَّق من كل `sources[].quote` حرفيًا في الملف المحدد ببصمة ذلك المصدر عند الإصدار والاستيراد؛ لا يُقبل الحكم إذا تعذّر التحقق.

## الاختبارات المطلوبة لكل عقد (FR-004)

- **المُنتِج**: ناتجه على العينة يجتاز المخطط والمُتحقِّق.
- **المستهلك**: يقبل عينة صحيحة، ويرفض: حقلًا زائدًا، ومسارًا مطلقًا في حقل نصي، و`synthetic: false`، وإصدار عقد غير معروف.
- **التغيير غير المتوافق**: عقد `v2` جديد مع اختبار مُنتِج ومستهلك وخطة ترحيل (المبدأ VI).

## المعرّفات

- `tender_id`: `NT-YYYY-NNNN`، يصدره NMIS وحده.
- `report_id`: `RR-` + 12 خانة سداسية.
- `finding_key`: SHA-256 لـ (`tender_id`، `criterion_id`، موضع الدليل) — هوية التكرار.
- `locator`: `p<فقرة>` أو `t<جدول>:r<صف>c<عمود>` داخل ملف Word.
