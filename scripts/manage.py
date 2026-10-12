"""统一构建、启动、健康检查、停止；只管理记录且属于本项目的子进程。"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.runtime'
STATE.mkdir(exist_ok=True)
PID_FILE = STATE / 'processes.json'
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except ImportError:
    pass


def tool(name):
    found = shutil.which(name + '.cmd' if os.name == 'nt' and name in ['mvn', 'npm'] else name)
    if not found:
        raise SystemExit(f'缺少 {name}，请先安装并加入 PATH。')
    return found


def command(name, *args):
    value = [tool(name), *args]
    return [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/c', *value] if os.name == 'nt' and name in ['mvn', 'npm'] else value


def build():
    subprocess.run(command('mvn', '-q', 'verify'), cwd=ROOT / 'services/commerce', check=True)
    subprocess.run(command('npm', 'ci', '--no-audit', '--no-fund'), cwd=ROOT / 'apps/storefront', check=True)
    subprocess.run(command('npm', 'run', 'build'), cwd=ROOT / 'apps/storefront', check=True)


def status():
    ready = True
    for name, port, path in [('commerce', 19081, '/api/health'), ('assistant', 19082, '/health'), ('knowledge', 19083, '/health'), ('storefront', 5273, '/')]:
        try:
            with urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
                ok = response.status == 200
        except Exception:
            ok = False
        print(f'{name}: {"ready" if ok else "unavailable"}')
        ready &= ok
    return ready


def start():
    if PID_FILE.exists():
        raise SystemExit('已有进程记录。请先运行 status 或 stop，避免重复启动。')
    jar = ROOT / 'services/commerce/target/commerce-1.0.0.jar'
    if not jar.exists():
        raise SystemExit('尚未构建，请执行 python scripts/manage.py build。')
    running_jar = STATE / 'commerce-1.0.0.jar'
    for port in [19081, 19082, 19083, 5273]:
        import socket
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'端口 {port} 已被占用。')
    shutil.copy2(jar, running_jar)
    services = [
        ('knowledge', [sys.executable, '-m', 'uvicorn', 'curated_knowledge.api:app', '--host', '127.0.0.1', '--port', '19083'], ROOT / 'services/knowledge'),
        ('assistant', [sys.executable, '-m', 'uvicorn', 'curated_assistant.api:app', '--host', '127.0.0.1', '--port', '19082'], ROOT / 'services/assistant'),
        ('commerce', [tool('java'), '-jar', str(running_jar)], ROOT),
        ('storefront', command('npm', 'run', 'dev'), ROOT / 'apps/storefront'),
    ]
    records = []
    for name, args, cwd in services:
        with (STATE / f'{name}.log').open('ab') as log:
            process = subprocess.Popen(args, cwd=cwd, env=os.environ.copy(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, start_new_session=os.name != 'nt')
        records.append({'name': name, 'pid': process.pid, 'root': str(ROOT), 'command': subprocess.list2cmdline(args)})
        PID_FILE.write_text(json.dumps(records), encoding='utf-8')
        print(f'{name} started (pid={process.pid})')
    print('访问 http://127.0.0.1:5273；日志位于 .runtime/；运行 status 查看健康状态。')


def stop():
    if not PID_FILE.exists():
        print('没有本项目的进程记录。')
        return
    records = json.loads(PID_FILE.read_text(encoding='utf-8'))
    refused = []
    for record in records:
        if record.get('root') != str(ROOT):
            raise SystemExit('进程记录不属于当前项目，停止操作已取消。')
        pid = int(record['pid'])
        if os.name == 'nt':
            # 验证工作进程命令行，防止 PID 复用后误停其他应用。
            result = subprocess.run(['powershell', '-NoProfile', '-Command', f'[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; (Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine'], capture_output=True, text=True, encoding='utf-8', errors='replace')
            line = result.stdout.strip().lower()
            expected = record.get('command', '').lower()
            recognized = bool(expected) and line == expected
            if recognized:
                subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif line:
                refused.append(record)
                print(f'{record["name"]}: 命令行与记录不一致，未停止')
                continue
        else:
            cmdline = Path(f'/proc/{pid}/cmdline')
            cwd = Path(f'/proc/{pid}/cwd')
            if cmdline.exists() and cwd.resolve().is_relative_to(ROOT):
                import signal
                os.killpg(pid, signal.SIGTERM)
        print(f'{record["name"]}: stop checked')
    if refused:
        PID_FILE.write_text(json.dumps(refused), encoding='utf-8')
    else:
        PID_FILE.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'start', 'status', 'stop'])
    parsed = parser.parse_args()
    {'build': build, 'start': start, 'status': status, 'stop': stop}[parsed.action]()
