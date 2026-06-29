"""
Lightweight translation layer. Strings are looked up by key in nested
dictionaries. The active language is persisted via settings.py.

Adding a language: copy the ``en`` block, translate the values, and
register it in ``LANGUAGES`` below.
"""

from __future__ import annotations

import locale
from typing import Any

import settings as user_settings


LANGUAGES = {
    "en": "English",
    "th": "ไทย",
}


_T: dict[str, dict[str, str]] = {
    "en": {
        # Common
        "common.save": "Save",
        "common.cancel": "Cancel",
        "common.close": "Close",
        "common.refresh": "Refresh",
        "common.ok": "OK",
        "common.browse": "Browse…",
        "common.add": "Add…",
        "common.rename": "Rename",
        "common.remove": "Remove",

        # Status / tooltip
        "status.token_error": "⚠ Token not found",
        "status.paused": "⏸ Paused (schedule)",
        "status.fetching": "⏳ Fetching…",
        "status.api_error": "⚠ API error",
        "status.no_data": "No data",
        "status.token_error_tooltip": "Token error — right-click for details",
        "status.paused_tooltip": "Paused (outside scheduled hours)",
        "status.fetching_tooltip": "Fetching…",
        "status.error_tooltip": "Error: {msg}",
        "status.no_headers": "No rate-limit headers in response.",
        "status.no_account": "No account configured.",
        "status.fetching_msg": "Fetching usage data…",
        "status.unknown_error": "Unknown error",

        # Bar / labels
        "bar.session_label": "5-hour limit",
        "bar.weekly_label": "Weekly limit",
        "bar.session_short": "5-hour",
        "bar.weekly_short": "Weekly",
        "bar.opus_short": "Opus wk",
        "bar.opus_label": "Weekly Opus limit",
        "bar.no_data": "No data yet",
        "bar.resets_in": "resets in {time}",
        "bar.resets_unknown": "resets — unknown",
        "bar.burn_collecting": "Burn rate: collecting…",
        "bar.burn_full_in": "{label}: +{rate:.1f}%/h · full in {eta}",
        "bar.burn_no_eta": "{label}: +{rate:.1f}%/h",

        # Notifications
        "toast.token_error_title": "{app} — Token error",
        "toast.api_error_title": "{app} — API error",
        "toast.heads_up_title": "{app}: heads up",
        "toast.heads_up_body": "{label} limit at {pct}%",
        "toast.error_title": "{app} error",
        "toast.setup_title": "{app} — Sign in required",
        "toast.setup_body": (
            "No login found. Sign in to Claude Desktop, or install Claude Code "
            "and run 'claude auth login'. You can also set Account → Manage accounts."
        ),

        # Menu
        "menu.show_status": "Show status",
        "menu.show_history": "Show history…",
        "menu.open_history": "Open full history…",
        "menu.refresh_now": "Refresh now",
        "menu.restart": "Restart",
        "menu.show_last_error": "Show last error",
        "menu.open_error_log": "Open error log…",
        "menu.copy_status": "Copy status to clipboard",
        "menu.snooze_alerts": "Snooze alerts (1 hour)",
        "menu.desktop_widget": "Desktop widget",
        "menu.desktop_widget_enable": "Show on-screen bar",
        "menu.tray_metric": "Tray icon shows",
        "menu.metric_session": "5-hour limit",
        "menu.metric_weekly": "Weekly limit",
        "menu.metric_max": "Higher of the two",
        "menu.notify_on_update": "Notify when update available",
        "menu.account": "Account",
        "menu.manage_accounts": "Manage accounts…",
        "menu.settings": "Settings",
        "menu.alert_thresholds": "Alert thresholds",
        "menu.thresholds_quiet": "Quiet (95%)",
        "menu.thresholds_default": "Default (80, 95)",
        "menu.thresholds_sensitive": "Sensitive (50, 75, 90)",
        "menu.thresholds_custom": "Custom…",
        "menu.sound_alerts": "Sound alerts",
        "menu.pause_outside": "Pause outside {start}:00–{end}:00",
        "menu.schedule_settings": "Schedule settings…",
        "menu.icon_theme": "Icon theme",
        "menu.theme_auto": "Auto",
        "menu.theme_light": "Light",
        "menu.theme_dark": "Dark",
        "menu.icon_style": "Icon style",
        "menu.style_frame": "Frame",
        "menu.style_solid": "Solid",
        "menu.style_donut": "Donut",
        "menu.style_bar": "Bar",
        "menu.poll_interval": "Poll interval",
        "menu.interval_auto": "Auto (adaptive)",
        "menu.interval_30s": "30 seconds",
        "menu.interval_1m": "1 minute",
        "menu.interval_2m": "2 minutes",
        "menu.interval_5m": "5 minutes",
        "menu.weekly_summary": "Export weekly summary…",
        "menu.monthly_summary": "Export monthly summary…",
        "menu.language": "Language",
        "menu.open_console": "Open Anthropic Console",
        "menu.console_usage": "Usage dashboard",
        "menu.console_limits": "Rate limits",
        "menu.maintenance": "Install / update",
        "menu.check_update": "Check for updates",
        "menu.apply_update": "Install latest release…",
        "menu.update_source": "Update source (GitHub repo)…",
        "menu.open_releases": "Open releases page",
        "menu.run_setup": "Run Setup (first install)",
        "menu.run_update_bat": "Run Update script",
        "menu.run_uninstall": "Uninstall…",
        "menu.open_install_folder": "Open install folder",
        "menu.quit": "Quit {app}",

        # Auth / re-auth
        "menu.reauth": "Re-authenticate (fix 401)…",
        "toast.reauth_title": "{app} — Re-authenticating",
        "toast.reauth_body": "Opening Claude Desktop… will retry in 15 s. If the icon stays red, click Refresh after signing in.",
        "toast.reauth_ok": "Token refreshed successfully.",
        "toast.reauth_failed": "Token still invalid. Open Claude Desktop, sign in, then click Refresh.",
        "toast.auth_expired_title": "{app} — Session expired",
        "toast.auth_expired_body": "Claude Desktop token expired. Will retry in 30 s. Or right-click → Re-authenticate.",
        "toast.token_refreshing": "Token near expiry — refreshing…",
        "toast.reset_soon_title": "{app} — Quota almost back",
        "toast.reset_soon_body": "{label} ({pct}%) resets in {time} — you'll be able to use it again soon.",
        "toast.status_copied": "Status copied to clipboard.",
        "toast.alerts_snoozed": "Alerts snoozed for 1 hour.",
        "toast.summary_saved": "Usage summary saved: {path}",
        "toast.summary_empty": "Not enough history yet for a summary.",
        "toast.summary_retention": "History retention raised to {days} days so future monthly summaries are complete.",

        "summary.title": "Usage summary",
        "summary.account": "Account",
        "summary.generated": "Generated",
        "summary.range": "Range (last {days} days)",
        "summary.samples": "Samples recorded",
        "summary.peak_session": "Peak 5-hour utilisation",
        "summary.peak_weekly": "Peak weekly utilisation",
        "summary.peak_opus": "Peak weekly Opus utilisation",
        "summary.busiest_hour": "Busiest hour of day",
        "summary.threshold_hits": "Times at/above {pct}%",
        "summary.no_data": "No history recorded in this range.",

        "health.source": "Source",
        "health.expires": "Token expires",
        "health.expires_in": "in {time}",
        "health.expired": "expired",

        "toast.update_checking": "Checking GitHub for updates…",
        "toast.update_error": "Update check failed: {msg}",
        "toast.update_available": "Update available: v{version}",
        "toast.update_up_to_date": "Up to date (v{version})",
        "toast.update_no_releases": "No releases published yet on this repo.",
        "toast.update_applied": "Update: {msg}",

        "dialog.update_source_title": "Claude Quota — Update source",
        "dialog.update_source_heading": "GitHub repository",
        "dialog.update_source_desc": (
            "Releases are downloaded from this repo (owner/repo or full github.com URL). "
            "Example: robonin9/claude-quota-tray"
        ),
        "dialog.update_source_invalid": "Enter owner/repo or a github.com URL.",
        "dialog.apply_update_title": "Install update",
        "dialog.apply_update_confirm": (
            "Download the latest release from GitHub and update this install?\n\n"
            "Repo: {repo}\n"
            "The app will close and restart when finished."
        ),
        "dialog.uninstall_confirm": (
            "Run the uninstall script?\n\n"
            "This removes the startup shortcut and virtual environment."
        ),

        # Window titles
        "window.history_title": "Claude Quota — {name}",
        "window.status_title": "Claude Quota — {name}",
        "window.current_usage": "Current usage",
        "window.last_24h": "Last 24 hours",
        "window.history_range": "History range",
        "window.range_24h": "24 hours",
        "window.range_7d": "7 days",
        "window.range_30d": "30 days",
        "window.chart_hover": "{time} · {pct}%",
        "window.export_csv": "Export CSV…",
        "window.export_title": "Export history",
        "window.export_ok": "Saved to {path}",
        "window.no_history": "No history yet — keep the tray running for a few minutes.",
        "status.last_poll": "Updated {ago}",

        # Plan badge
        "plan.label": "Plan",
        "plan.unknown": "Unknown",

        # Accounts dialog
        "dialog.accounts_title": "Claude Quota — Accounts",
        "dialog.accounts_heading": "Configured accounts",
        "dialog.accounts_desc": (
            "Each account points to a Claude Code credentials file. "
            "“Default” auto-discovers credentials (Claude Desktop, Claude Code file, "
            "Windows Credential Manager, or CLAUDE_CODE_OAUTH_TOKEN)."
        ),
        "dialog.accounts_no_selection": "Select an account first.",
        "dialog.accounts_keep_one": "At least one account must remain.",
        "dialog.accounts_remove_confirm": "Remove “{name}”?",
        "dialog.accounts_rename": "Rename",
        "dialog.accounts_rename_title": "Rename account",
        "dialog.accounts_rename_label": "New name:",
        "dialog.accounts_remove_title": "Remove account",
        "dialog.accounts_add_title": "Add account",
        "dialog.accounts_field_name": "Account name",
        "dialog.accounts_field_mode": "Mode",
        "dialog.accounts_mode_auto": "Auto-discover",
        "dialog.accounts_mode_file": "Credentials file…",
        "dialog.accounts_field_path": "Credentials file",
        "dialog.accounts_browse_title": "Select credentials.json",
        "dialog.accounts_missing_path": "Pick a credentials file or switch to Auto-discover.",

        # Schedule dialog
        "dialog.schedule_title": "Claude Quota — Schedule",
        "dialog.schedule_heading": "Polling schedule",
        "dialog.schedule_desc": "When enabled, the tray pauses API polling outside the hours and days you select below.",
        "dialog.schedule_enable": "Enable scheduled polling",
        "dialog.schedule_hours": "Active hours:",
        "dialog.schedule_days": "Active days",

        # Days (short)
        "day.mon": "Mon",
        "day.tue": "Tue",
        "day.wed": "Wed",
        "day.thu": "Thu",
        "day.fri": "Fri",
        "day.sat": "Sat",
        "day.sun": "Sun",

        # Thresholds dialog
        "dialog.thresholds_title": "Claude Quota — Alert thresholds",
        "dialog.thresholds_heading": "Alert thresholds",
        "dialog.thresholds_desc": "Notification fires when usage crosses any of these percentages.\nEnter values separated by commas (e.g., 50, 75, 90).",
        "dialog.thresholds_play_sound": "Play sound on alert",
        "dialog.thresholds_invalid": "Enter integer percentages between 1 and 100.",
        "dialog.thresholds_empty": "Enter at least one threshold.",
    },
    "th": {
        # Common
        "common.save": "บันทึก",
        "common.cancel": "ยกเลิก",
        "common.close": "ปิด",
        "common.refresh": "รีเฟรช",
        "common.ok": "ตกลง",
        "common.browse": "เลือกไฟล์…",
        "common.add": "เพิ่ม…",
        "common.rename": "เปลี่ยนชื่อ",
        "common.remove": "ลบ",

        # Status / tooltip
        "status.token_error": "⚠ ไม่พบ Token",
        "status.paused": "⏸ หยุดชั่วคราว (ตามตาราง)",
        "status.fetching": "⏳ กำลังโหลด…",
        "status.api_error": "⚠ API ผิดพลาด",
        "status.no_data": "ไม่มีข้อมูล",
        "status.token_error_tooltip": "ไม่พบ Token — คลิกขวาเพื่อดูรายละเอียด",
        "status.paused_tooltip": "หยุดชั่วคราว (อยู่นอกเวลาที่ตั้งไว้)",
        "status.fetching_tooltip": "กำลังโหลด…",
        "status.error_tooltip": "ผิดพลาด: {msg}",
        "status.no_headers": "ไม่พบ rate-limit headers จาก response",
        "status.no_account": "ยังไม่ได้ตั้งค่าบัญชี",
        "status.fetching_msg": "กำลังโหลดข้อมูลโควต้า…",
        "status.unknown_error": "ผิดพลาดไม่ทราบสาเหตุ",

        # Bar / labels
        "bar.session_label": "ลิมิตรอบ 5 ชั่วโมง",
        "bar.weekly_label": "ลิมิตรายสัปดาห์",
        "bar.session_short": "5 ชม.",
        "bar.weekly_short": "รายสัปดาห์",
        "bar.opus_short": "Opus/สัปดาห์",
        "bar.opus_label": "ลิมิต Opus รายสัปดาห์",
        "bar.no_data": "ยังไม่มีข้อมูล",
        "bar.resets_in": "รีเซ็ตในอีก {time}",
        "bar.resets_unknown": "รีเซ็ต — ไม่ทราบเวลา",
        "bar.burn_collecting": "อัตราการใช้: กำลังเก็บข้อมูล…",
        "bar.burn_full_in": "{label}: +{rate:.1f}%/ชม. · เต็มในอีก {eta}",
        "bar.burn_no_eta": "{label}: +{rate:.1f}%/ชม.",

        # Notifications
        "toast.token_error_title": "{app} — ไม่พบ Token",
        "toast.api_error_title": "{app} — API ผิดพลาด",
        "toast.heads_up_title": "{app}: แจ้งเตือน",
        "toast.heads_up_body": "{label} ใช้ไปแล้ว {pct}%",
        "toast.error_title": "{app} ผิดพลาด",
        "toast.setup_title": "{app} — ต้องเข้าสู่ระบบก่อน",
        "toast.setup_body": (
            "ไม่พบการ login — กรุณาเข้าสู่ระบบใน Claude Desktop "
            "หรือติดตั้ง Claude Code แล้วรัน 'claude auth login' "
            "หรือตั้งค่า Account → จัดการบัญชี"
        ),

        # Menu
        "menu.show_status": "ดูสถานะ",
        "menu.show_history": "ดูประวัติ…",
        "menu.open_history": "เปิดประวัติเต็ม…",
        "menu.refresh_now": "รีเฟรชเดี๋ยวนี้",
        "menu.restart": "รีสตาร์ท",
        "menu.show_last_error": "ดู error ล่าสุด",
        "menu.open_error_log": "เปิด error.log…",
        "menu.copy_status": "คัดลอกสถานะ",
        "menu.snooze_alerts": "เลื่อนแจ้งเตือน (1 ชม.)",
        "menu.desktop_widget": "แถบบนจอ",
        "menu.desktop_widget_enable": "แสดงแถบบนจอ",
        "menu.tray_metric": "ไอคอน tray แสดง",
        "menu.metric_session": "โควตา 5 ชม.",
        "menu.metric_weekly": "โควตารายสัปดาห์",
        "menu.metric_max": "ค่าที่สูงกว่า",
        "menu.notify_on_update": "แจ้งเมื่อมีอัปเดต",
        "menu.account": "บัญชี",
        "menu.manage_accounts": "จัดการบัญชี…",
        "menu.settings": "ตั้งค่า",
        "menu.alert_thresholds": "เกณฑ์แจ้งเตือน",
        "menu.thresholds_quiet": "เงียบ (95%)",
        "menu.thresholds_default": "ปกติ (80, 95)",
        "menu.thresholds_sensitive": "ละเอียด (50, 75, 90)",
        "menu.thresholds_custom": "กำหนดเอง…",
        "menu.sound_alerts": "เสียงแจ้งเตือน",
        "menu.pause_outside": "หยุดนอกเวลา {start}:00–{end}:00",
        "menu.schedule_settings": "ตั้งค่าตาราง…",
        "menu.icon_theme": "ธีมไอคอน",
        "menu.theme_auto": "อัตโนมัติ",
        "menu.theme_light": "สว่าง",
        "menu.theme_dark": "มืด",
        "menu.icon_style": "รูปแบบไอคอน",
        "menu.style_frame": "กรอบ",
        "menu.style_solid": "ทึบ",
        "menu.style_donut": "โดนัท",
        "menu.style_bar": "แถบ",
        "menu.poll_interval": "ความถี่ในการเช็ค",
        "menu.interval_auto": "อัตโนมัติ (ปรับตามการใช้)",
        "menu.interval_30s": "30 วินาที",
        "menu.interval_1m": "1 นาที",
        "menu.interval_2m": "2 นาที",
        "menu.interval_5m": "5 นาที",
        "menu.weekly_summary": "ส่งออกสรุปรายสัปดาห์…",
        "menu.monthly_summary": "ส่งออกสรุปรายเดือน…",
        "menu.language": "ภาษา",
        "menu.open_console": "เปิด Anthropic Console",
        "menu.console_usage": "Dashboard การใช้งาน",
        "menu.console_limits": "Rate limits",
        "menu.maintenance": "ติดตั้ง / อัปเดต",
        "menu.check_update": "ตรวจสอบอัปเดต",
        "menu.apply_update": "ติดตั้งเวอร์ชันล่าสุด…",
        "menu.update_source": "แหล่งอัปเดต (GitHub repo)…",
        "menu.open_releases": "เปิดหน้า Releases",
        "menu.run_setup": "รัน Setup (ติดตั้งครั้งแรก)",
        "menu.run_update_bat": "รันสคริปต์ Update",
        "menu.run_uninstall": "ถอนการติดตั้ง…",
        "menu.open_install_folder": "เปิดโฟลเดอร์ติดตั้ง",
        "menu.quit": "ออกจาก {app}",

        # Auth / re-auth
        "menu.reauth": "ยืนยันตัวตนใหม่ (แก้ 401)…",
        "toast.reauth_title": "{app} — กำลังยืนยันตัวตนใหม่",
        "toast.reauth_body": "กำลังเปิด Claude Desktop… จะลองใหม่ใน 15 วิ ถ้าไอคอนยังแดงอยู่ให้ login แล้วคลิก Refresh",
        "toast.reauth_ok": "รีเฟรช Token สำเร็จ",
        "toast.reauth_failed": "Token ยังไม่ถูกต้อง — เปิด Claude Desktop แล้ว login จากนั้นกด Refresh",
        "toast.auth_expired_title": "{app} — Session หมดอายุ",
        "toast.auth_expired_body": "Token ของ Claude Desktop หมดอายุ จะลองใหม่ใน 30 วิ หรือคลิกขวา → ยืนยันตัวตนใหม่",
        "toast.token_refreshing": "Token ใกล้หมดอายุ — กำลังรีเฟรช…",
        "toast.reset_soon_title": "{app} — โควต้าใกล้กลับมาแล้ว",
        "toast.reset_soon_body": "{label} ({pct}%) จะรีเซ็ตในอีก {time} — อีกสักครู่จะใช้ได้อีกครั้ง",
        "toast.status_copied": "คัดลอกสถานะไปยังคลิปบอร์ดแล้ว",
        "toast.alerts_snoozed": "เลื่อนการแจ้งเตือนไป 1 ชั่วโมงแล้ว",
        "toast.summary_saved": "บันทึกสรุปการใช้งานแล้ว: {path}",
        "toast.summary_empty": "ข้อมูลยังไม่พอสำหรับทำสรุป",
        "toast.summary_retention": "ขยายการเก็บประวัติเป็น {days} วัน เพื่อให้สรุปรายเดือนครั้งต่อไปครบถ้วน",

        "summary.title": "สรุปการใช้งาน",
        "summary.account": "บัญชี",
        "summary.generated": "สร้างเมื่อ",
        "summary.range": "ช่วงเวลา ({days} วันล่าสุด)",
        "summary.samples": "จำนวนตัวอย่างที่บันทึก",
        "summary.peak_session": "การใช้สูงสุดรอบ 5 ชม.",
        "summary.peak_weekly": "การใช้สูงสุดรายสัปดาห์",
        "summary.peak_opus": "การใช้ Opus สูงสุดรายสัปดาห์",
        "summary.busiest_hour": "ชั่วโมงที่ใช้หนักสุด",
        "summary.threshold_hits": "จำนวนครั้งที่ถึง/เกิน {pct}%",
        "summary.no_data": "ไม่มีประวัติในช่วงเวลานี้",

        "health.source": "แหล่ง",
        "health.expires": "Token หมดอายุ",
        "health.expires_in": "ในอีก {time}",
        "health.expired": "หมดอายุแล้ว",

        "toast.update_checking": "กำลังตรวจสอบอัปเดตจาก GitHub…",
        "toast.update_error": "ตรวจสอบอัปเดตไม่สำเร็จ: {msg}",
        "toast.update_available": "มีเวอร์ชันใหม่: v{version}",
        "toast.update_up_to_date": "เป็นเวอร์ชันล่าสุดแล้ว (v{version})",
        "toast.update_no_releases": "repo นี้ยังไม่มี release เผยแพร่",
        "toast.update_applied": "อัปเดต: {msg}",

        "dialog.update_source_title": "Claude Quota — แหล่งอัปเดต",
        "dialog.update_source_heading": "GitHub repository",
        "dialog.update_source_desc": (
            "ดาวน์โหลด release จาก repo นี้ (รูปแบบ owner/repo หรือ URL github.com เต็ม) "
            "เช่น robonin9/claude-quota-tray"
        ),
        "dialog.update_source_invalid": "กรุณาใส่ owner/repo หรือ URL github.com",
        "dialog.apply_update_title": "ติดตั้งอัปเดต",
        "dialog.apply_update_confirm": (
            "ดาวน์โหลด release ล่าสุดจาก GitHub และอัปเดตการติดตั้งนี้?\n\n"
            "Repo: {repo}\n"
            "แอปจะปิดแล้วเริ่มใหม่เมื่อเสร็จ"
        ),
        "dialog.uninstall_confirm": (
            "รันสคริปต์ถอนการติดตั้ง?\n\n"
            "จะลบ shortcut ใน Startup และ virtual environment"
        ),

        # Window titles
        "window.history_title": "Claude Quota — {name}",
        "window.status_title": "Claude Quota — {name}",
        "window.current_usage": "การใช้งานปัจจุบัน",
        "window.last_24h": "ย้อนหลัง 24 ชั่วโมง",
        "window.history_range": "ช่วงเวลา",
        "window.range_24h": "24 ชั่วโมง",
        "window.range_7d": "7 วัน",
        "window.range_30d": "30 วัน",
        "window.chart_hover": "{time} · {pct}%",
        "window.export_csv": "ส่งออก CSV…",
        "window.export_title": "ส่งออกประวัติ",
        "window.export_ok": "บันทึกที่ {path}",
        "window.no_history": "ยังไม่มีประวัติ — ปล่อยให้แอปทำงานสักพักก่อน",
        "status.last_poll": "อัปเดต {ago}",

        # Plan badge
        "plan.label": "แพคเกจ",
        "plan.unknown": "ไม่ทราบ",

        # Accounts dialog
        "dialog.accounts_title": "Claude Quota — บัญชี",
        "dialog.accounts_heading": "บัญชีที่ตั้งค่าไว้",
        "dialog.accounts_desc": (
            "แต่ละบัญชีชี้ไปที่ไฟล์ credentials ของ Claude Code "
            "โหมด “Default” จะค้นหาอัตโนมัติ (Claude Desktop, ไฟล์ Claude Code, "
            "Windows Credential Manager หรือ CLAUDE_CODE_OAUTH_TOKEN)"
        ),
        "dialog.accounts_no_selection": "กรุณาเลือกบัญชีก่อน",
        "dialog.accounts_keep_one": "ต้องมีบัญชีอย่างน้อย 1 รายการ",
        "dialog.accounts_remove_confirm": "ลบ “{name}” ใช่หรือไม่?",
        "dialog.accounts_rename": "เปลี่ยนชื่อ",
        "dialog.accounts_rename_title": "เปลี่ยนชื่อบัญชี",
        "dialog.accounts_rename_label": "ชื่อใหม่:",
        "dialog.accounts_remove_title": "ลบบัญชี",
        "dialog.accounts_add_title": "เพิ่มบัญชี",
        "dialog.accounts_field_name": "ชื่อบัญชี",
        "dialog.accounts_field_mode": "โหมด",
        "dialog.accounts_mode_auto": "ค้นหาอัตโนมัติ",
        "dialog.accounts_mode_file": "เลือกไฟล์ credentials…",
        "dialog.accounts_field_path": "ไฟล์ credentials",
        "dialog.accounts_browse_title": "เลือกไฟล์ credentials.json",
        "dialog.accounts_missing_path": "กรุณาเลือกไฟล์ หรือสลับเป็นค้นหาอัตโนมัติ",

        # Schedule dialog
        "dialog.schedule_title": "Claude Quota — ตารางเวลา",
        "dialog.schedule_heading": "ตารางเวลาการเช็ค",
        "dialog.schedule_desc": "เมื่อเปิด แอปจะหยุดเรียก API นอกเหนือจากช่วงเวลาและวันที่เลือกไว้",
        "dialog.schedule_enable": "เปิดใช้ตารางเวลา",
        "dialog.schedule_hours": "ช่วงเวลาทำงาน:",
        "dialog.schedule_days": "วันที่ทำงาน",

        # Days (short)
        "day.mon": "จ",
        "day.tue": "อ",
        "day.wed": "พ",
        "day.thu": "พฤ",
        "day.fri": "ศ",
        "day.sat": "ส",
        "day.sun": "อา",

        # Thresholds dialog
        "dialog.thresholds_title": "Claude Quota — เกณฑ์แจ้งเตือน",
        "dialog.thresholds_heading": "เกณฑ์การแจ้งเตือน",
        "dialog.thresholds_desc": "ระบบจะแจ้งเตือนเมื่อใช้งานถึงเปอร์เซ็นต์ที่กำหนด\nคั่นด้วยจุลภาค (เช่น 50, 75, 90)",
        "dialog.thresholds_play_sound": "เล่นเสียงเมื่อแจ้งเตือน",
        "dialog.thresholds_invalid": "กรุณาใส่เปอร์เซ็นต์เป็นจำนวนเต็มระหว่าง 1–100",
        "dialog.thresholds_empty": "กรุณาใส่อย่างน้อย 1 ค่า",
    },
}


def _detect_default() -> str:
    try:
        loc = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        loc = ""
    return "th" if loc.startswith("th") else "en"


def current_language() -> str:
    lang = user_settings.get("language")
    if not lang or lang not in _T:
        return _detect_default()
    return lang


def set_language(lang: str) -> None:
    if lang not in _T:
        return
    user_settings.update(language=lang)


def t(key: str, **kwargs: Any) -> str:
    """Translate a key. Falls back to English, then to the raw key."""
    lang = current_language()
    text = _T.get(lang, {}).get(key) or _T["en"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
