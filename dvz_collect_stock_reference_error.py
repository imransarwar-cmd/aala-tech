#!/usr/bin/env python3
"""Read recent Odoo logs for one FK failure. No database connection or writes."""
import configparser
import glob
from pathlib import Path
import re
import subprocess

SERVICE = 'odoo19v2.service'
NEEDLE = 'stock_reference_move_rel_move_id_fkey'


def run(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=25)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def option(args, *names):
    for index, arg in enumerate(args):
        for name in names:
            if arg == name and index + 1 < len(args):
                return args[index + 1]
            if arg.startswith(name + '='):
                return arg.split('=', 1)[1]
    return ''


def excerpts(text):
    lines = text.splitlines()
    matches = [i for i, line in enumerate(lines) if NEEDLE in line][-4:]
    positions = set()
    for i in matches:
        positions.update(range(max(0, i - 6), min(len(lines), i + 13)))
    result = []
    previous = -2
    for i in sorted(positions):
        if i != previous + 1:
            result.append('---')
        line = lines[i]
        # Withhold entire credential-bearing lines rather than attempting to
        # redact just a portion of an unfamiliar log format.
        if re.search(r'password|passwd|api_key|authorization|access_token', line, re.I):
            line = '[credential-bearing log line withheld]'
        result.append(line)
        previous = i
    return '\n'.join(result)


def main():
    pid = run('systemctl', 'show', SERVICE, '--property=MainPID', '--value')
    args = []
    cwd = Path('/opt/odoo19')
    if pid.isdigit() and int(pid) > 0:
        try:
            args = [x.decode(errors='replace') for x in Path('/proc', pid, 'cmdline').read_bytes().split(b'\0') if x]
            cwd = Path('/proc', pid, 'cwd').resolve()
        except OSError:
            pass
    configured = option(args, '-c', '--config')
    configs = [configured] if configured else ['/etc/odoo19.conf']
    logs = set()
    print('Read-only log collection. No database connection, changes, or service restart.')
    print('Service:', SERVICE, '| PID:', pid or 'unavailable')
    for name in configs:
        path = Path(name)
        if not path.is_absolute():
            path = cwd / path
        print('Config:', path, '(running process)' if configured else '(fallback; not confirmed)')
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            with path.open() as stream:
                cfg.read_file(stream)
            for key in ('db_name', 'db_host', 'db_port'):
                print(key + ':', cfg.get('options', key, fallback='[not explicitly set]'))
            logfile = cfg.get('options', 'logfile', fallback='').strip()
            if logfile and logfile.lower() not in ('false', 'none'):
                path = Path(logfile)
                logs.add(path if path.is_absolute() else cwd / path)
        except (OSError, configparser.Error) as exc:
            print('Cannot read configuration:', type(exc).__name__)
    override = option(args, '--logfile')
    if override:
        path = Path(override)
        logs.add(path if path.is_absolute() else cwd / path)
    for pattern in ('/opt/odoo19/log/*.log', '/opt/odoo19/log/*.log.1', '/var/log/odoo*.log', '/var/log/odoo*/*.log'):
        logs.update(Path(p) for p in glob.glob(pattern))
    found = False
    for path in sorted(logs):
        if not path.is_file():
            continue
        try:
            with path.open('rb') as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - 8 * 1024 * 1024))
                data = stream.read().decode(errors='replace')
            snippet = excerpts(data)
            if snippet:
                print('\nSOURCE:', path, '\n' + snippet)
                found = True
        except OSError as exc:
            print('Cannot read log:', path, type(exc).__name__)
    journal = run('journalctl', '-u', SERVICE, '--since', '6 hours ago', '-n', '6000', '--no-pager', '-o', 'short-iso')
    snippet = excerpts(journal)
    if snippet:
        print('\nSOURCE: systemd journal\n' + snippet)
        found = True
    if not found:
        print('\nNo matching entry in the recent log sections searched. No repair was attempted.')
        print('Check that this is the same server/service that produced the browser error.')
    else:
        print('\nCollection complete. Review excerpts for private information before sharing.')


if __name__ == '__main__':
    main()
