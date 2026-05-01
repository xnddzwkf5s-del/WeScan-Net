#!/usr/bin/env python3
"""
WeScan Daily Health Report
Sends a daily server health summary to vwoo@outlook.com.au via Mailgun.
"""
import os
import subprocess
import shutil
import requests
from datetime import datetime


# ── Config ────────────────────────────────────────────────────────────────────

MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY', '')
MAILGUN_DOMAIN  = os.getenv('MAILGUN_DOMAIN', 'wescan.net')
TO_EMAIL        = 'vwoo@outlook.com.au'
FROM_EMAIL      = f'WeScan Health <noreply@{MAILGUN_DOMAIN}>'

DISK_WARN_PCT   = 80   # warn if disk usage % exceeds this
MEM_WARN_PCT    = 85   # warn if memory usage % exceeds this
LOAD_WARN       = 2.0  # warn if 15-min load average exceeds this
SERVICES        = ['wescan', 'nginx', 'postfix']


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return '(error)'


def pct_bar(pct, width=20):
    filled = int(width * pct / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f'[{bar}] {pct:.1f}%'


# ── Collect metrics ───────────────────────────────────────────────────────────

def get_disk():
    rows = []
    for line in run("df -h --output=source,size,used,avail,pcent,target -x tmpfs -x devtmpfs").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6:
            rows.append(parts)
    return rows


def get_memory():
    total = int(run("awk '/MemTotal/ {print $2}' /proc/meminfo"))
    free  = int(run("awk '/MemAvailable/ {print $2}' /proc/meminfo"))
    used  = total - free
    pct   = used / total * 100
    swap_total = int(run("awk '/SwapTotal/ {print $2}' /proc/meminfo"))
    swap_free  = int(run("awk '/SwapFree/ {print $2}' /proc/meminfo"))
    swap_used  = swap_total - swap_free
    return {
        'total_mb': total // 1024,
        'used_mb':  used  // 1024,
        'free_mb':  free  // 1024,
        'pct':      pct,
        'swap_total_mb': swap_total // 1024,
        'swap_used_mb':  swap_used  // 1024,
    }


def get_load():
    data = run("cat /proc/loadavg").split()
    return {
        '1min':  float(data[0]),
        '5min':  float(data[1]),
        '15min': float(data[2]),
        'procs': data[3],
    }


def get_uptime():
    return run("uptime -p")


def get_services():
    results = {}
    for svc in SERVICES:
        status = run(f"systemctl is-active {svc}")
        results[svc] = status
    return results


def get_mail_queue():
    active   = run("postqueue -p 2>/dev/null | grep -c '^[A-F0-9]' || echo 0")
    deferred = run("postqueue -p 2>/dev/null | grep -c 'deferred' || echo 0")
    try:
        return int(active), int(deferred)
    except Exception:
        return 0, 0


def get_top_procs():
    return run("ps aux --sort=-%cpu | awk 'NR==1 || NR<=6' | awk '{printf \"%-15s %5s %5s\\n\", $11, $3, $4}'")


def get_recent_errors():
    return run("grep -c 'ERROR' /var/log/wescan/error.log 2>/dev/null || echo 0")


def get_db_size():
    return run("du -sh /opt/wescan/wescan.db 2>/dev/null || echo 'N/A'").split()[0]


def get_backups():
    return run("ls -1t /tmp/wescan-pre-deploy-*.tar.gz 2>/dev/null | head -3 || echo '(none)'")


# ── Build report ──────────────────────────────────────────────────────────────

def build_report():
    now      = datetime.now().strftime('%A, %d %b %Y %H:%M UTC')
    disk     = get_disk()
    mem      = get_memory()
    load     = get_load()
    uptime   = get_uptime()
    services = get_services()
    q_active, q_deferred = get_mail_queue()
    top_procs = get_top_procs()
    errors   = get_recent_errors()
    db_size  = get_db_size()
    backups  = get_backups()

    # ── Alerts ──
    alerts = []
    for row in disk:
        pct_str = row[4].replace('%', '')
        try:
            if int(pct_str) >= DISK_WARN_PCT:
                alerts.append(f'⚠️  DISK {row[5]} is {row[4]} full ({row[2]} / {row[1]})')
        except Exception:
            pass
    if mem['pct'] >= MEM_WARN_PCT:
        alerts.append(f'⚠️  MEMORY usage is {mem["pct"]:.1f}% ({mem["used_mb"]} MB / {mem["total_mb"]} MB)')
    if load['15min'] >= LOAD_WARN:
        alerts.append(f'⚠️  LOAD AVERAGE (15m) is {load["15min"]} — system may be under stress')
    for svc, status in services.items():
        if status != 'active':
            alerts.append(f'🔴 SERVICE {svc} is {status.upper()}')
    if q_deferred > 5:
        alerts.append(f'⚠️  MAIL QUEUE has {q_deferred} deferred messages')

    alert_block = ''
    if alerts:
        alert_block = '\n🚨 ALERTS\n' + '─' * 40 + '\n' + '\n'.join(alerts) + '\n'

    # ── Disk section ──
    disk_lines = ['Mount        Size   Used  Avail  Use%']
    for row in disk:
        disk_lines.append(f"{row[5]:<12} {row[1]:>5} {row[2]:>6} {row[3]:>6}  {row[4]:>4}")
    disk_block = '\n'.join(disk_lines)

    # ── Memory section ──
    mem_block = (
        f"RAM:   {mem['used_mb']:>6} MB used / {mem['total_mb']} MB total  {pct_bar(mem['pct'])}\n"
        f"Swap:  {mem['swap_used_mb']:>6} MB used / {mem['swap_total_mb']} MB total"
    )

    # ── Load section ──
    load_block = (
        f"Load:  {load['1min']} (1m)  {load['5min']} (5m)  {load['15min']} (15m)\n"
        f"Tasks: {load['procs']}\n"
        f"Up:    {uptime}"
    )

    # ── Services section ──
    svc_lines = []
    for svc, status in services.items():
        icon = '✅' if status == 'active' else '🔴'
        svc_lines.append(f"  {icon}  {svc:<12} {status}")
    svc_block = '\n'.join(svc_lines)

    # ── Mail queue section ──
    mail_block = f"  Active:   {q_active}\n  Deferred: {q_deferred}"

    # ── Compose ──
    report = f"""WeScan Daily Health Report
{now}
{'═' * 44}
{alert_block}
💾 DISK USAGE
{'─' * 40}
{disk_block}

🧠 MEMORY
{'─' * 40}
{mem_block}

⚙️  CPU & LOAD
{'─' * 40}
{load_block}

🔧 SERVICES
{'─' * 40}
{svc_block}

📬 MAIL QUEUE (Postfix)
{'─' * 40}
{mail_block}

📁 DATABASE
{'─' * 40}
  wescan.db:  {db_size}
  Errors (log): {errors}

💾 RECENT DEPLOY BACKUPS
{'─' * 40}
{backups}

🔝 TOP PROCESSES (by CPU%)
{'─' * 40}
{top_procs}

{'─' * 44}
wescan.net  |  170.64.232.39  |  auto-report
"""
    return report, bool(alerts)


# ── Send ──────────────────────────────────────────────────────────────────────

def send_report(report, has_alerts):
    subject = '🔴 WeScan Health Alert' if has_alerts else '✅ WeScan Daily Health Report'
    resp = requests.post(
        f'https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages',
        auth=('api', MAILGUN_API_KEY),
        data={
            'from':    FROM_EMAIL,
            'to':      TO_EMAIL,
            'subject': subject,
            'text':    report,
        },
        timeout=15
    )
    if resp.status_code == 200:
        print(f'Report sent to {TO_EMAIL}')
    else:
        print(f'Mailgun error {resp.status_code}: {resp.text}')


if __name__ == '__main__':
    # Load .env
    env_path = '/opt/wescan/.env'
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    os.environ.setdefault(k.strip(), v.strip())

    MAILGUN_API_KEY = os.getenv('MAILGUN_API_KEY', '')
    MAILGUN_DOMAIN  = os.getenv('MAILGUN_DOMAIN', 'wescan.net')

    report, has_alerts = build_report()
    print(report)
    send_report(report, has_alerts)
