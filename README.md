# منظومة النور — Noor Tender Suite

> منظومة لدورة العروض الهندسية: من رصد المنافسة، إلى سجلها ومهام الفريق، إلى بناء العرض الفني ومراجعته بالدليل.
> **الحالة (2026-10-24):** قيد البناء لعرض الهاكاثون الهندسي 2026 — التحدي 05: العروض الهندسية المتقدمة (مسار التطوير الهندسي).
> بيانات العينة الجديدة للمواصفة 001 **مصطنعة**؛ ولم يكتمل الخيط بعد. الشركة الظاهرة في بيانات العرض («النور») كيان افتراضي.

---

## ما الذي يُبنى الآن (المواصفة 001: «الخيط الواحد»)

نبني **خيطًا عاملًا واحدًا** على منافسة مصطنعة. صُممت نسخة العرض للعمل محليًا على جهاز واحد بلا اتصال خارجي، ويُتحقق من ذلك عند اكتمالها:

```
الرادار ← سجل المنافسة في NMIS (البيت) ← ATPAS (عرض Word) ← JoUReady (فحوص حتمية + ختم SHA-256) ← الثغرات إلى NMIS
```

| المكوّن | الدور في الخيط | الحالة الآن |
|---|---|---|
| حزمة العقود `packages/noor_contracts/` | ستة عقود JSON مُرقَّمة (`noor.*/v1`) ومُتحقِّق يرفض المسارات المحلية ومعرّفات الجلسات | قيد البناء |
| NMIS `platforms/nmis/` | البيت: سجل المنافسات، الصلاحيات، الاعتماد البشري، المهام | قيد البناء (الأساس) |
| الرادار `platforms/radar/` | تصدير منافسة مرشَّحة بعقد | لم يُنقل بعد (ينتظر فحص بوابته) |
| ATPAS `platforms/atpas/` | بناء عرض Word عربي من سجل المنافسة | لم يُنقل بعد (ينتظر فحص بوابته) |
| JoUReady `platforms/jouready/` | فحوص حتمية + «فحص إحالات SBC المحدود» + ملف ختم | لم يُنقل بعد (ينتظر فحص بوابته) |

### ما لن يُعرض في هذه المرحلة (إفصاح)

- تحليل الجداول الزمنية XER ومحاكاة مونت كارلو: **مؤجلان**.
- «فحص إحالات SBC المحدود» يفحص الإحالات فقط، **ولا يحقق المطابقة الهندسية الكاملة**.
- لا حكم بنموذج ذكاء اصطناعي في الخيط؛ الفحوص حتمية، وكل نتيجة «مقترحة» حتى يعتمدها إنسان مصرَّح له.
- التحليل السريع ليس جزءًا من الخيط العامل.
- الختم تحقق من سلامة الملفات، **ليس توقيعًا ولا إثباتًا لهوية المُصدر**.
- تطوّر الفكرة من ثلاث وحدات مسجّلة إلى خمس، مع استبدال وحدة التدقيق بـ JoUReady: **تأكيده مع المرشدين لم يُحسم بعد**.

## الأرقام

لا نذكر في هذا الملف رقمًا (عدد اختبارات، دقة، زمن) إلا بتعريفه وعينته وتاريخه وطريقة إعادة إنتاجه ونتيجته.
حتى الآن: **غير مُقاس**. ستُضاف الأرقام هنا بعد أول تشغيل موثّق.

## النسخة السابقة

النسخة السابقة (FastAPI + Next.js) **ليست جزءًا من هذا المستودع**، ولا تُستعمل في المواصفتين 001 و002.
الادعاءات التي كانت تُنشر عن تلك النسخة (عدد الوكلاء، عدد الاختبارات، «MVP مكتمل»، نتيجة تدقيق أمني) **أُزيلت لأنها غير موثّقة بدليل قابل لإعادة الإنتاج**.

## البدء من نسخة مستنسخة حديثًا

المتطلبات: Windows 11 · PowerShell · Python 3.11+ · Node.js 24. من جذر المستودع، أنشئ بيئة Python وثبّت حزم التشغيل والاختبار:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e packages/noor_contracts -e packages/noor_identity -e packages/noor_sso/python -e packages/noor_runtime flask jsonschema python-docx cryptography==50.0.2 pytest
$env:PYTHONPATH = (@('platforms/nmis', 'packages/noor_identity', 'packages/noor_sso/python') -join [IO.Path]::PathSeparator)
mkdir .pytest_tmp
$env:PYTHONIOENCODING = 'utf-8'
.venv\Scripts\python.exe -m pytest packages/noor_contracts packages/noor_identity packages/noor_sso/tests/test_verify.py packages/noor_runtime platforms/nmis/tests tools/tests -q -p no:cacheprovider --basetemp=.pytest_tmp/codexfix
node --test packages/noor_sso/tests/verify.test.mjs packages/noor_sso/tests/guards.test.mjs packages/noor_sso/tests/fixtures.mjs packages/noor_runtime/tests/netguard.test.mjs
```

يتضمن تثبيت حزمة SSO مكتبة `cryptography`. لتجهيز العرض، ولّد مفاتيح التوقيع في مجلد خارج المستودع:

```powershell
.venv\Scripts\python.exe -m noor_registry.keys generate --out-dir <folder outside repo>
```

قبل تشغيل `launcher/noor-demo.ps1`، اضبط في جلسة PowerShell المتغيرات `NOOR_DATA_DIR` و`NOOR_EXCHANGE_DIR` و`NOOR_IDENTITY_DIR` (مجلدات خارج المستودع)، و`NOOR_HOME_SIGNING_KEY_FILE` (مسار ملف المفتاح المُولّد خارج المستودع)، و`NOOR_SECRET_KEY`، و`NOOR_PW_PROPOSAL_MANAGER` و`NOOR_PW_REVIEW_APPROVER` و`NOOR_PW_MEMBER` و`NOOR_PW_VIEWER`. استعمل قيمًا سرية خاصة بك ولا تضعها في المستودع. ثم شغّل `powershell -ExecutionPolicy Bypass -File launcher\noor-demo.ps1 -Seed` لإنشاء بيانات العرض، أو احذف `-Seed` للتشغيل العادي. يستمع التطبيق على `127.0.0.1` فقط.

قبل أي commit أو تسليم: `python tools/scan_public_repo.py --diff --require-blocklist` (أسرار، مسارات محلية، أسماء محظورة).
قائمة الأسماء المحظورة ملف خاص **خارج** المستودع يحدده `NOOR_BLOCKLIST_FILE`، ويفشل الفحص بدونه. فحص CI على GitHub لا يملك هذه القائمة، فهو **لا يتحقق من الأسماء**.

## الحوكمة

- الدستور: `.specify/memory/constitution.md` · القرارات: `.specify/memory/decisions.md`.
- المواصفة والخطة والمهام: `specs/001-single-thread-demo/`.
- منهجية التطوير بالمواصفات (GitHub Spec Kit): لا كود قبل المواصفة والخطة والمهام المعتمدة.

## English summary

Noor Tender Suite is being rebuilt for a 2026 engineering hackathon as one working thread on a **synthetic** tender:
radar → tender registry in NMIS (the "home") → ATPAS (Word proposal) → JoUReady (deterministic checks + SHA-256 seal file) → gaps back to NMIS.
The demo build is designed to run locally, listening on 127.0.0.1 only, with synthetic sample data; this is verified when the thread is complete. XER analysis and Monte Carlo simulation are deferred.
No performance or test-count figures are claimed yet ("not measured"). The previous version (FastAPI + Next.js) is not part of this repository.

## License

© 2026 Youssef Seleim. All rights reserved. The source is published for evaluation only; no license is granted to copy, modify, distribute, or use it without written permission.
