# vitals

> العلامات الحيوية لمشروعك، بلا شبكة.

إضافة (plugin) لـClaude Code يجري **جرد استمرارية قطعياً وبلا شبكة** لأي مجلد مشروع: هل الملفات المطلوبة موجودة، وهل كل مجلد عنصر يلتزم بعقده، وهل الحقائق المسجلة ما زالت صالحة، وهل ملفات الحالة بحداثة الشغل، وهل ملف مشتق انحرف عن مصادره.

- بلا شبكة وبلا اعتماديات (بايثون 3.8+ المكتبة القياسية فقط).
- قراءة فقط (يكتب تقريراً فقط إذا مررت `--report`).
- إعداد لكل مشروع بملف JSON واحد، فلا حاجة لنسخ الأداة بين المشاريع.

English: [README.md](README.md)

## التثبيت

```
/plugin marketplace add msamkari/samkari-plugins
/plugin install vitals@samkari-plugins
```

ثم اطلب من Claude: «شغّل vitals».

## بدون Claude

```
python -X utf8 scripts/vitals.py <project_root> [--config FILE] [--report FILE]
```

رمز الخروج: `0` لا FAIL، `2` على الأقل FAIL، `1` خطأ في الأداة (الإعداد مفقود أو غير صالح أو وسائط خاطئة). WARN لا يفشل.

## الإعداد (`<root>/Jobs/inventory.config.json`)

انظر [examples/inventory.config.example.json](examples/inventory.config.example.json). المفاتيح: `required_files`، `items` (أو `episodes`)، `facts_files` و`facts_soon_days`، `state_fresh`، `newest_age`، `sync` (شرحها بالجدول في README الإنجليزي).

عالج النتائج بتحديث الملفات المتأخرة، لا بتعديل الإعداد لإخفائها.

## الأمان

لا ينفّذ ملفات المشروع ولا يفتح اتصالات ولا يكتب شيئاً إلا ملف `--report` الاختياري ولا يخزّن مفاتيح. مسارات الإعداد مدخلات موثوقة: استعمل مسارات نسبية داخل المشروع.

## الاختبارات

```
python -m unittest discover -s tests -v
```

## الترخيص

MIT.
