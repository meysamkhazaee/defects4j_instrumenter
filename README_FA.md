# ابزار اینسترومنت و تولید دیتاسِت Defects4J (جاوا)

[![Version](https://img.shields.io/badge/version-1.3.5-blue.svg)](file:///D:/personal/defects4j_instrumenter/VERSION)
[![Changelog](https://img.shields.io/badge/changelog-available-green.svg)](file:///D:/personal/defects4j_instrumenter/CHANGELOG.md)

این پروژه یک فریم‌ورک مستقل، خودکار و دقیق برای اینسترومنت کردن برنامه‌های جاوا در بنچ‌مارک **Defects4J** و استخراج مسیرهای اجرایی (Execution Traces) با نقاط گره‌ای `P` است. فرمت خروجی‌های این پروژه دقیقاً متناظر و هم‌شکل با بنچ‌مارک زیمنس تولید می‌شود.

---

## 🎯 ویژگی‌های کلیدی

1. **اینسترومنت در سطح بایت‌کد (Java Agent):**
   - بر پایه استاندارد `java.lang.instrument` و کتابخانه دستکاری بایت‌کد **ASM**.
   - تزریق پروب‌های لاگ‌گیری (`TraceRuntime.record(predicateId)`) بدون دستکاری فایل‌های سورس جاوا بر روی دیسک.
2. **کشف درستی تصادفی (Coincidental Correctness - CC):**
   - تحلیل خطوط تغییریافته و باگ‌دار با گیت‌دیف خودکار (`source_changes.json`).
   - نگاشت دقیق شماره خطوط به گره‌های `P` در فایل `source_map.csv`.
   - تست‌های موفقی که از روی مکان خطا عبور کرده‌اند شناسایی شده و با برچسب `CC` مشخص می‌شوند.
3. **تولید دیتاست‌های استاندارد مشابه زیمنس:**
   - تولید فایل‌های `_dataset.txt` و `_tagged.txt` و `_detailed.json` با قالبی یکسان.
   - حفظ سازگاری با فرمت CSV مرحله دوم پروژه EFL (`cmp.v0.v*.csv`).

---

## 📁 ساختار پوشه‌ها

```text
defects4j_instrumenter/
├── java-agent/                         # سورس کدهای Java Agent و اسکریپت‌های بیلد JAR
│   ├── src/main/java/org/efl/defects4j/
│   │   ├── agent/                      # کدهای رهگیری بایت‌کد، نگاشت پردیکیت‌ها و ران‌تایم
│   │   └── tools/                      # اسکن کلاس‌ها و شمارش تست‌ها
│   └── build.py                        # کامپایل خودکار جاوا ایجنت
├── defects4j_efl_instrumenter/         # پکیج اصلی پایتون برای مدیریت اجرا
│   ├── runner.py                       # کنترل اجرای موازی، تست‌ها و تجمیع
│   ├── trace.py                        # ساخت دیتاست‌های ماتریسی P و برچسب‌های CC
│   ├── patch.py                        # نگاشت خطاهای سورس کد
│   └── ...
├── scripts/                            # اسکریپت‌های کمکی برای لینوکس (build_agent.sh, test_all.sh)
├── tests/                              # تست‌های واحد
├── run.sh                              # رانر اصلی اجرایی لینوکس
├── run_defects4j.py                    # اسکریپت پایتون
└── README.md                           # راهنمای انگلیسی
```

---

## 📊 فرمت دیتاسِت‌های خروجی

برای هر نسخه خطا (مثلاً `Lang-1`)، فایل‌های زیر در مسیر خروجی تولید می‌شوند:

### ۱. فایل `v<id>_dataset.txt` (فرمت ماتریسی ساده)
سطرهای ۱ تا N نشان‌دهنده دنباله نقاط `P` در مسیر اجرای هر تست بوده و سطر آخر بردار وضعیت نتایج (`T` یا `F`) است:
```text
P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P6,P7,P10,P12
P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P10,P12
P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P9,P10,P12
T,T,T,F,T,F,F,T,T,T
```

### ۲. فایل `v<id>_tagged.txt` (همراه با تفکیک تست‌های CC)
مشابه فایل قبل، با این تفاوت که در سطر آخر تست‌هایی که با وجود عبور از خطای کد پاس شده‌اند با تگ `CC` تفکیک شده‌اند:
```text
P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P6,P7,P10,P12
P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P10,P12
P1,P2,P3,P4,P4,P3,P4,P4,P2,P3,P4,P4,P3,P4,P4,P5,P9,P10,P12
T,T,CC,F,T,CC,F,T,T,T
```

### ۳. فایل `v<id>_detailed.json` (اطلاعات کامل و متادیتا)
شامل زمان اجرا، گره‌های باگ، آمار تست‌های Pass و Fail و CC، و مسیر کامل هر تست.

---

## 🛠️ نحوه اجرا در لینوکس

### ۱. نصب پیش‌نیازها در اوبونتو / دبیان:
```bash
sudo apt update && sudo apt install -y openjdk-11-jdk git subversion perl cpanminus curl unzip
```

### ۲. اجرای تفکیک‌شده و پرسرعت (پیشنهادی بر اساس سرعت پروژه‌ها):

برای جلوگیری از طولانی شدن اجرا، پیشنهاد می‌شود پروژه‌ها را به صورت لایه‌بندی شده (Tiered) اجرا کنید و حتماً از گزینه `--test-selection relevant` استفاده کنید:

```bash
# --- لایه ۱: پروژه‌های فوق‌العاده سریع (کل اجرا حدود ۱۵ تا ۳۰ دقیقه) ---
./run.sh --projects Csv,Codec,Gson,Chart,Time --test-selection relevant --jobs 8

# --- لایه ۲: پروژه‌های پایه و اصلی مقالات (حدود ۱ تا ۲ ساعت) ---
./run.sh --projects Lang,Math --test-selection relevant --jobs 8

# --- لایه ۳: پروژه‌های متوسط (حدود ۱ تا ۲ ساعت) ---
./run.sh --projects Cli,Collections,Compress,JacksonCore,JacksonXml,JxPath --test-selection relevant --jobs 8

# --- لایه ۴: پروژه‌های سنگین (اجرای مجزا در طول شب) ---
./run.sh --projects Mockito --test-selection relevant --jobs 8
./run.sh --projects Jsoup --test-selection relevant --jobs 8
./run.sh --projects JacksonDatabind --test-selection relevant --jobs 8
./run.sh --projects Closure --test-selection relevant --jobs 8
```

### ۳. کامندهای اجرای تک‌باگ، پروفایل مقاله و کل بنچ‌مارک:

```bash
# ۱. اجرای یک باگ خاص (مثلاً باگ ۱ پروژه Lang):
./run.sh --projects Lang --bugs 1

# ۲. اجرای چند باگ خاص با موازی‌سازی (مثلاً باگ‌های ۱، ۲ و ۵ پروژه Math):
./run.sh --projects Math --bugs 1,2,5 --jobs 4

# ۳. اجرای کل ۳۹۵ باگ پروفایل استاندارد مقاله (scd4fl-2024 روی ۶ پروژه اصلی):
./run.sh --profile scd4fl-2024 --test-selection relevant --jobs 8 --timeout 60

# ۴. اجرای تمام ۱۷ پروژه و همه ۸۳۸ باگ Defects4J 3.0.1 (پوشش حداکثری و نهایی):
./run.sh --test-selection relevant --jobs 8 --timeout 60

# ۵. اجرای مستقیم با پایتون:
python3 run_defects4j.py --projects Lang --bugs 1
```

---

### ۴. تفاوت پروفایل‌ها و حالات انتخاب تست:

* **دامنه بنچ‌مارک (Benchmark Scope):**
  - **پروژه‌های ۶گانه کلاسیک (۳۹۵ باگ - پیش‌فرض مقالات FL):** `Chart: 26`, `Closure: 133`, `Lang: 65`, `Math: 106`, `Mockito: 38`, `Time: 27`.
  - **پروژه‌های ۱۱گانه تکمیلی (۴۴۳ باگ):** `Csv: 16`, `Codec: 18`, `Gson: 18`, `JxPath: 22`, `JacksonCore: 26`, `JacksonXml: 6`, `Collections: 28`, `Cli: 40`, `Compress: 47`, `Jsoup: 93`, `JacksonDatabind: 112`.
  - **مجموع:** ۱۷ پروژه و ۸۳۸ باگ واقعی.

* **حالات انتخاب تست دیتا (`--test-selection <mode>`):**
  - **`relevant` (بسیار سریع و استاندارد ۵۰x-۱۰۰x):** اجرای تست‌های مرتبط با کلاس‌های تغییریافته (شامل تمام مسیرهای Pass، CC و Fail).
  - **`trigger` (دیباگ سریع):** فقط تست‌های فیل‌شده (۱ تا ۳ تست برای هر باگ).
  - **`all` (بسیار کند):** اجرای تمام چند هزار تست کل مخزن (استفاده از آن برای کل ۸۳۸ باگ اصلاً توصیه نمی‌شود چون هفته‌ها زمان می‌برد).

---

### ۵. نسخه و تاریخچه تغییرات (Versioning & Changelog):

نسخه این پروژه به‌صورت متمرکز در فایل [VERSION](file:///D:/personal/defects4j_instrumenter/VERSION) ذخیره شده و تمامی بخش‌های زیر از آن رفرنس می‌گیرند:
- پیکربندی پکیج در `pyproject.toml`
- پکیج پایتون `defects4j_efl_instrumenter` (`__version__`)
- اسکریپت کامپایل ایجنت جاوا (`java-agent/build.py`) و متادیتای `MANIFEST.MF`
- اسکریپت‌های اجرایی `run_defects4j.py` و CLI با فلگ `--version`

برای مشاهده تاریخچه کامل نسخه‌ها و تغییرات به [CHANGELOG.md](file:///D:/personal/defects4j_instrumenter/CHANGELOG.md) مراجعه نمایید.

