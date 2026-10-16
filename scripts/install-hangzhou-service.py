"""安装当前用户的 Supervisor 服务与开机启动；不需要 root，不修改其他服务。"""
import argparse
import shlex
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, default=Path.home() / 'mahjong-web')
parser.add_argument('--port', type=int, default=8866)
parser.add_argument('--llm-gateway-config', type=Path, help='仓库外的 LLM Gateway 凭据 JSON 文件')
args = parser.parse_args()
root = args.root.resolve()
assert 1024 <= args.port <= 65535
assert (root / 'current/server/app.py').is_file()
assert (root / 'venv/bin/supervisord').is_file()
assert ' ' not in str(root) and '%' not in str(root), '部署目录不能包含空格或 %'
(root / 'logs').mkdir(exist_ok=True)
config = root / 'supervisord.conf'
environment = 'PYTHONUNBUFFERED="1",PYTHONDONTWRITEBYTECODE="1"'
if args.llm_gateway_config:
    credential_path = args.llm_gateway_config.resolve()
    assert credential_path.is_file()
    assert not any(c in str(credential_path) for c in ('"', '%', '\n', '\r', ','))
    environment += f',LLM_GATEWAY_CONFIG_FILE="{credential_path}"'
config.write_text(f'''[unix_http_server]
file={root}/supervisor.sock
chmod=0600

[supervisord]
logfile={root}/logs/supervisord.log
logfile_maxbytes=10MB
logfile_backups=3
pidfile={root}/supervisord.pid
childlogdir={root}/logs
umask=027

[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix://{root}/supervisor.sock

[program:mahjong-web]
directory={root}/current
command={root}/venv/bin/python -m uvicorn server.app:app --host 0.0.0.0 --port {args.port} --workers 1 --no-access-log --limit-concurrency 32
environment={environment}
autostart=true
autorestart=true
startsecs=5
startretries=3
stopasgroup=true
killasgroup=true
stopsignal=TERM
stopwaitsecs=30
stdout_logfile={root}/logs/app.stdout.log
stdout_logfile_maxbytes=10MB
stdout_logfile_backups=3
stderr_logfile={root}/logs/app.stderr.log
stderr_logfile_maxbytes=10MB
stderr_logfile_backups=3
''')
config.chmod(0o600)
start = root / 'start-service.sh'
start.write_text(f'''#!/bin/sh
set -eu
umask 027
exec 9>{shlex.quote(str(root / 'start.lock'))}
/usr/bin/flock -n 9 || exit 0
if {root}/venv/bin/supervisorctl -c {config} pid >/dev/null 2>&1; then
    exit 0
fi
{root}/venv/bin/supervisord -c {config}
''')
start.chmod(0o700)
old = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
if old.returncode not in (0, 1) or (old.returncode == 1 and 'no crontab' not in old.stderr):
    raise RuntimeError(old.stderr)
marker = '# mahjong-web 自启动'
lines = [line for line in old.stdout.splitlines() if not line.endswith(marker)]
lines.append(f'@reboot {start} >> {root}/logs/boot.log 2>&1 {marker}')
subprocess.run(['crontab', '-'], input='\n'.join(lines) + '\n', text=True, check=True)
subprocess.run([str(start)], check=True)
print(f'服务配置：{config}；端口：{args.port}', flush=True)
