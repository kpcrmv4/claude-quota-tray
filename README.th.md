# Claude Quota Tray — คู่มือภาษาไทย

<p align="center">
  <img src="assets/hero.png" width="900" alt="Claude Quota Tray — ดูโควต้า Claude แบบเรียลไทม์บน Windows tray" />
</p>

แอปเล็กๆ บน **system tray** (มุมขวาล่างของ Windows) ที่บอกว่าโควต้า Claude ของคุณเหลือเท่าไหร่ — ทั้ง **5-hour (Session)** และ **Weekly** — โดยไม่ต้องเปิดเว็บหรือ Claude Desktop ทุกครั้ง

> เอกสารฉบับนี้เน้น **วิธีใช้ + คำแนะนำ** สำหรับผู้ใช้ทั่วไป  
> รายละเอียดเทคนิค / โครงสร้างโค้ด → ดู [README.md](README.md) · สิ่งที่เปลี่ยนในแต่ละเวอร์ชัน → [CHANGELOG.md](CHANGELOG.md)

---

## สารบัญ

1. [แอปนี้เหมาะกับใคร](#แอปนี้เหมาะกับใคร)
2. [สิ่งที่ต้องมีก่อนติดตั้ง](#สิ่งที่ต้องมีก่อนติดตั้ง)
3. [แนะนำวิธีติดตั้ง (เลือกแบบไหน)](#แนะนำวิธีติดตั้ง-เลือกแบบไหน)
4. [เริ่มต้นใช้งาน — 5 นาทีแรก](#เริ่มต้นใช้งาน--5-นาทีแรก)
5. [ฟีเจอร์หลักและวิธีใช้](#ฟีเจอร์หลักและวิธีใช้)
6. [คำแนะนำการตั้งค่า](#คำแนะนำการตั้งค่า)
7. [ไอคอน Taskbar vs Tray](#ไอคอน-taskbar-vs-tray)
8. [อัปเดตและย้ายไปเครื่องอื่น](#อัปเดตและย้ายไปเครื่องอื่น)
9. [แก้ปัญหาที่พบบ่อย](#แก้ปัญหาที่พบบ่อย)
10. [ความปลอดภัยและข้อมูลส่วนตัว](#ความปลอดภัยและข้อมูลส่วนตัว)

---

## แอปนี้เหมาะกับใคร

- ใช้ **Claude Code** หรือ **Claude Desktop** อยู่แล้ว และอยากรู้ว่าโควต้า 5 ชม. / รายสัปดาห์ใกล้เต็มหรือยัง
- ทำงานหลายบัญชี (หลาย credentials) แล้วอยากสลับดูได้จาก tray
- อยากได้ **การแจ้งเตือน** ก่อนโควต้าเต็ม โดยไม่ต้องจำเปิดเว็บ

แอป **ไม่** แทนที่การสมัคร Claude — ใช้ OAuth ที่คุณล็อกอินไว้แล้วเท่านั้น

---

## สิ่งที่ต้องมีก่อนติดตั้ง

| รายการ | รายละเอียด |
|--------|------------|
| **ระบบปฏิบัติการ** | Windows 10 / 11 (แนะนำ) — macOS 13+ รองรับแบบเบต้า |
| **บัญชี Claude** | ล็อกอินอย่างน้อยหนึ่งทาง: [Claude Desktop](https://claude.ai/download) หรือ Claude Code (`claude auth login`) |
| **อินเทอร์เน็ต** | ใช้เรียก `api.anthropic.com` เป็นระยะ (ประมาณทุก 1 นาที ตามการตั้งค่า) |

แอปจะ **ค้นหา token อัตโนมัติ** จาก Claude Desktop, Credential Manager, หรือไฟล์ credentials ของ Claude Code — ไม่ต้องสร้าง API key แยก

---

## แนะนำวิธีติดตั้ง (เลือกแบบไหน)

| วิธี | เหมาะกับ | ข้อดี | ข้อควรรู้ |
|------|---------|-------|-----------|
| **Setup + source** (แนะนำ) | ผู้ใช้ทั่วไป, กลัว antivirus | ดับเบิ้ลคลิก `Setup claude quota tray.bat` — ติด Python + venv ให้เอง | หลัง `build.bat` ให้รัน Setup อีกครั้งเพื่อไอคอน taskbar สวย |
| **.exe จาก Releases** | อยากย้ายแค่ไฟล์เดียว | ไม่ต้องมี Python บนเครื่อง | Defender อาจเตือน unknown publisher → More info → Run anyway |
| **Build เอง** | นักพัฒนา / fork | ควบคุมเวอร์ชันและ sign ได้ | ต้องมี Python + `requirements-dev.txt` |

### ขั้นตอนติดตั้งแบบแนะนำ (Windows)

1. ดาวน์โหลด ZIP จาก [Releases](../../releases/latest) หรือ `Code → Download ZIP` แล้วแตกโฟลเดอร์
2. ดับเบิ้ลคลิก **`Setup claude quota tray.bat`**
   - ถ้าไม่มี Python → script จะติดตั้ง Python 3.13 แบบ per-user (ไม่ต้อง admin)
   - สร้าง `.venv`, ติด dependencies, สร้าง shortcut ใน Startup
3. (แนะนำ) ดับเบิ้ลคลิก **`build.bat`** เพื่อสร้าง `dist\ClaudeQuotaTray.exe`
4. รัน **Setup อีกครั้ง** — shortcut จะชี้ไปที่ `.exe` แทน `pythonw.exe`
5. ดับเบิ้ลคลิก **`Run claude quota tray.bat`** หรือรีสตาร์ทเครื่อง

ไฟล์ `.bat` สำคัญ:

| ไฟล์ | ใช้เมื่อไหร่ |
|------|-------------|
| `Setup claude quota tray.bat` | ติดตั้งครั้งแรก / สร้าง shortcut ใหม่ |
| `Run claude quota tray.bat` | เปิดแอปด้วยตัวเอง (เลือก `.exe` ก่อนถ้ามี) |
| `Update claude quota tray.bat` | อัปเดต dependencies หลังแทนที่ source |
| `Uninstall claude quota tray.bat` | ลบ shortcut + venv (+ ถามลบข้อมูลผู้ใช้) |

---

## เริ่มต้นใช้งาน — 5 นาทีแรก

1. **ล็อกอิน Claude** — เปิด Claude Desktop หรือรัน `claude auth login` ใน Claude Code อย่างน้อยครั้งหนึ่ง
2. **รันแอป** — หลัง Setup ไอคอน % ควรโผล่ที่ tray (มุมขวาล่าง)
3. **ถ้าไม่เห็นไอคอน** — ดู [แก้ปัญหา: ไม่เห็น tray](#ไม่เห็นไอคอนใน-system-tray)
4. **คลิกซ้ายที่ไอคอน** — หน้าต่างเล็กแสดงหลอด Session + Weekly, burn rate, เวลา reset
5. **คลิกขวา** — เมนูตั้งค่า, ประวัติ, บัญชี, อัปเดต

ภาษาเมนู: ตาม locale ของ Windows (ไทย/อังกฤษ) — ปรับได้ใน Settings ถ้ามีตัวเลือกภาษา

---

## ฟีเจอร์หลักและวิธีใช้

<p align="center">
  <img src="assets/features.png" width="900" alt="ฟีเจอร์ต่างๆ" />
</p>

### ไอคอน Tray (มุมขวาล่าง)

- แสดง **เปอร์เซ็นต์การใช้** บนไอคอน — สีเปลี่ยนตามระดับ (เขียว → เหลือง → ส้ม → แดง)
- **คลิกซ้าย** → หน้าต่างสถานะแบบกะทัดรัด
- **คลิกขวา** → เมนูเต็ม พร้อม progress bar แบบ Unicode ในเมนู

**Settings → Icon style** — เลือกรูปแบบไอคอน (กรอบ / ทึบ / โดนัท / แถบ)  
**Settings → Tray icon shows** — เลือกว่าจะแสดง % จาก Session, Weekly หรือค่าสูงสุดของทั้งสอง

<p align="center">
  <img src="assets/preview.png" width="760" alt="ไอคอน tray ปรับแต่งได้ 4 สไตล์ (กรอบ / ทึบ / โดนัท / แถบ)" />
</p>

<p align="center">
  <img src="assets/tray-menu.png" width="760" alt="เมนูคลิกขวา พร้อม progress bar ในเมนู" />
</p>

### ประวัติและกราฟ

- เมนู **History** → กราฟ **Session** และ **Weekly** แยกแผง
- สลับช่วง **24 ชั่วโมง / 7 วัน / 30 วัน (รายเดือน)**
- เลื่อนเมาส์บนกราฟเพื่อดูค่า % ของแต่ละช่วงเวลา
- **ส่งออก CSV** สำหรับวิเคราะห์เอง

> เลือก **30 วัน** ครั้งแรก แอปจะขยายเวลาเก็บประวัติให้อัตโนมัติ (เป็นอย่างน้อย 31 วัน เพิ่มขึ้นเท่านั้น) เพื่อให้กราฟรายเดือนมีข้อมูลครบ

<p align="center">
  <img src="assets/monthly.png" width="760" alt="กราฟรายเดือน 30 วัน — แนวโน้ม Session/Weekly ทั้งเดือน" />
</p>

ข้อมูลเก็บใน `history.db` ที่โฟลเดอร์ผู้ใช้ (ค่าเริ่มต้นเก็บ 7 วัน)

### Burn rate และ ETA

ในหน้าต่างสถานะจะบอกโดยประมาณว่า:

- ใช้ไปกี่ **%/ชั่วโมง**
- ถ้าใช้แบบนี้ต่อ จะ **เต็มเมื่อไหร่**

คำนวณจาก snapshot ใน SQLite — ยิ่งใช้นานยิ่งแม่นขึ้น

### การแจ้งเตือน

- แจ้งเมื่อข้ามเกณฑ์ที่ตั้ง (เช่น 80%, 95%)
- แยกเกณฑ์ **Session** และ **Weekly** ได้
- **เสียงเตือน** เปิด/ปิดได้ (Windows)
- **Snooze alerts** — ปิดการแจ้งเตือนชั่วคราว 1 ชม. จากเมนู

<p align="center">
  <img src="assets/alerts.png" width="760" alt="การแจ้งเตือน toast + ระดับสีตามเปอร์เซ็นต์การใช้งาน" />
</p>

### Desktop widget (Windows)

แถบ quota เล็กๆ ลอยบนจอ (always-on-top) — เปิดจากเมนู **Desktop widget**  
เหมาะถ้าอยากมองเห็นตลอดโดยไม่ต้องเปิด popup

### หลายบัญชี

**Account → Manage accounts…** — เพิ่ม path credentials หรือโหมด auto แล้วสลับบัญชีจากเมนู

### ตารางเวลา (Schedule)

**Settings → Schedule** — หยุด poll นอกเวลาทำงาน (เช่น จ–ศ 09:00–18:00) เพื่อลดการเรียก API ตอนไม่ได้ใช้

### อัปเดตจาก GitHub

คลิกขวา tray → **Install / update**:

- **Check for updates** — เทียบเวอร์ชันกับ Releases
- **Install latest release…** — ดาวน์โหลด zip หรือ `.exe` แล้วรีสตาร์ทเอง
- **Update source…** — ตั้ง repo เช่น `owner/claude-quota-tray`

---

## คำแนะนำการตั้งค่า

เปิด **คลิกขวา tray → Settings**

### สำหรับผู้ใช้ทั่วไป (เริ่มต้น)

| การตั้งค่า | แนะนำ | เหตุผล |
|-----------|--------|--------|
| Poll interval | **1 นาที** | สมดุลระหว่างทันสมัยกับการเรียก API |
| Alert thresholds | **Default (80 / 95)** | แจ้งก่อนเต็มพอมีเวลาหยุดใช้ |
| Sound alerts | **เปิด** | ได้ยินตอนทำงานอื่นอยู่ |
| Icon theme | **Auto** | ตามธีม Windows |
| Desktop widget | **ปิด** ก่อน | เปิดเมื่ออยากมองตลอจอ |
| Schedule | **ปิด** | เปิดถ้าอยากไม่ poll ตอนกลางคืน |

### ถ้าใช้ Claude หนักมาก

- ตั้งเกณฑ์ Session ต่ำกว่า Weekly (เช่น Session 60/80, Weekly 80/95)
- เปิด **History** ดูกราฟ 24 ชม. เป็นประจำ
- ใช้ **Snooze** เมื่อรู้ว่ากำลัง sprint งานและไม่อยากโดน toast รบกวน

### ถ้าใช้หลายเครื่อง

- แต่ละเครื่องมี `~/.claude-quota-tray/` ของตัวเอง — settings **ไม่ sync** อัตโนมัติ
- คัดลอก `settings.json` ได้ถ้าอยาก config เดียวกัน (ปิดแอปก่อนคัดลอก)

### ค่าใช้จ่าย API

แต่ละครั้งที่ poll ใช้คำขอสั้นๆ กับ Haiku (~1 token) — สำหรับผู้ใช้ subscription มักรวมในแพ็กเกจอยู่แล้ว  
ถ้ากังวล → ตั้ง poll เป็น **2–5 นาที** หรือเปิด Schedule

---

## ไอคอน Taskbar vs Tray

| ตำแหน่ง | มาจากไหน | หมายเหตุ |
|---------|----------|----------|
| **Tray** (ลูกศร ^) | วาดแบบ dynamic ตาม % | เปลี่ยนตาม Settings → Icon style |
| **Taskbar** (แถบด้านล่าง) | ไอคอนของ **process ที่รัน** | ถ้ารันผ่าน `pythonw.exe` มักเป็นไอคอน Python |

**วิธีให้ taskbar เป็นไอคอนแอป (กรอบ % สีเขียว):**

1. รัน `build.bat` ให้ได้ `dist\ClaudeQuotaTray.exe`
2. ปิดแอปเก่า (Quit จาก tray)
3. รัน `Setup claude quota tray.bat` อีกครั้ง
4. เปิดด้วย `Run claude quota tray.bat` หรือ `.exe` โดยตรง
5. ถ้าเคยปักหมุดไอคอน Python — ถอดแล้วปักหมุดจาก shortcut / `.exe` ใหม่

ไอคอน Start / Properties ของ shortcut ใช้ `assets/app.ico` — แต่ **taskbar ตอนรัน** ยังตาม process จริง

---

## อัปเดตและย้ายไปเครื่องอื่น

### อัปเดต (โหมด source)

1. แทนที่ไฟล์ในโฟลเดอร์ด้วย ZIP เวอร์ชันใหม่ (อย่าลบ `.venv` ถ้าไม่จำเป็น)
2. ดับเบิ้ลคลิก **`Update claude quota tray.bat`**
3. หรือใช้เมนู tray → **Install latest release…**

### ย้ายไปเครื่องใหม่

**แบบง่าย:** คัดลอกโฟลเดอร์ทั้งก้อน หรือแค่ `ClaudeQuotaTray.exe` แล้วรัน  
**แบบ source:** คัดลอกโฟลเดอร์ (ไม่ต้องคัดลอก `.venv`) → รัน Setup บนเครื่องใหม่

OAuth อยู่ที่เครื่องเดิม (Claude Desktop / Claude Code) — เครื่องใหม่ต้องล็อกอิน Claude เอง

### สิ่งที่ไม่ควรอัปโหลด GitHub

- `.venv/`, `dist/`, token, `settings.json`, `history.db`
- รายละเอียดเพิ่มใน [README.md](README.md) ส่วนความปลอดภัย

---

## แก้ปัญหาที่พบบ่อย

### ไม่เห็นไอคอนใน System Tray

Windows 11 มักซ่อนไอคอนแอปใหม่:

1. คลิกขวา **Taskbar** → **Taskbar settings**
2. **Other system tray icons** → เปิดรายการ
3. หา **Python** หรือ **ClaudeQuotaTray** → ตั้งเป็น **On**

<p align="center">
  <img src="assets/troubleshooting.png" width="900" alt="แก้ปัญหา tray" />
</p>

### ขึ้น "No credentials" / ไม่มีข้อมูล %

- ตรวจว่า Claude Desktop เปิดและล็อกอินแล้ว หรือรัน `claude auth login`
- **Account → Manage accounts** — ลองชี้ path ไฟล์ credentials เอง
- รัน diagnostic: `python src/token_reader.py --probe` (จากโฟลเดอร์ที่มี `.venv`)

### Taskbar ยังเป็นไอคอน Python

- ดู [ไอคอน Taskbar vs Tray](#ไอคอน-taskbar-vs-tray) — ต้องรันจาก `.exe` หลัง build + Setup ใหม่

### Windows Defender บล็อก .exe

- คลิก **More info** → **Run anyway** หรือใช้โหมด **Setup + source** แทน
- Maintainer สามารถ sign ด้วย OV/EV — ดู [docs/SIGNING.md](docs/SIGNING.md)

### แอปเปิดซ้ำไม่ได้ / ค้าง

- ปิดจาก tray → Quit หรือจบ process `pythonw.exe` / `ClaudeQuotaTray.exe` ใน Task Manager
- ลบ lock ไม่จำเป็น — แอปใช้ single-instance lock อัตโนมัติ

### ดู error

- เมนู tray → เปิด **error.log** (ถ้ามี)
- ไฟล์อยู่ที่ `%USERPROFILE%\.claude-quota-tray\error.log`

---

## ความปลอดภัยและข้อมูลส่วนตัว

- อ่าน OAuth token **จากเครื่องคุณเท่านั้น** — ไม่ส่งไปเซิร์ฟเวอร์อื่นนอก `api.anthropic.com` (HTTPS)
- **ไม่เก็บ** token ใน `settings.json` หรือ `history.db`
- History เก็บแค่ตัวเลข % กับเวลา
- โค้ดเปิด MIT — ตรวจสอบได้ทั้ง repo

---

## ลิงก์ที่เกี่ยวข้อง

| เอกสาร | เนื้อหา |
|--------|---------|
| [README.md](README.md) | ภาพรวมเทคนิค + โครงสร้างโปรเจกต์ (ภาษาไทย/ผสม) |
| [CHANGELOG.md](CHANGELOG.md) | บันทึกการเปลี่ยนแปลงแต่ละเวอร์ชัน |
| [docs/SIGNING.md](docs/SIGNING.md) | การ sign `.exe` (สำหรับ maintainer) |
| [Releases](../../releases/latest) | ดาวน์โหลด ZIP / `.exe` |

---

## เครดิต

- แนวคิดจาก [Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter) (เวอร์ชัน ESP32)
- Fork / พัฒนาต่อจาก [kpcrmv4/claude-quota-tray](https://github.com/kpcrmv4/claude-quota-tray)

**License:** MIT — ดูไฟล์ `LICENSE`
