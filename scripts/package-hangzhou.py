"""打包已构建的杭州麻将；记录工作区差异与逐文件 SHA，不修改 Git 暂存区。"""
import hashlib
import io
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
patch = subprocess.check_output(['git', 'diff', 'HEAD', '--binary'], cwd=root)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
release = f'{stamp}-{revision[:7]}'
files = [p for folder in ('server', 'dist') for p in (root / folder).rglob('*')
         if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo', '.so')]
files += [root / name for name in ('README.md', 'LICENSE', 'tests/arena/scenarios.json')]
assert (root / 'dist/index.html').is_file(), '请先运行 npm run build'
manifest = {'release': release, 'revision': revision, 'working_tree_patch_sha256': hashlib.sha256(patch).hexdigest(), 'files': {}}
for path in sorted(files):
    with path.open('rb') as stream:
        manifest['files'][path.relative_to(root).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
out = root / 'artifacts/deploy' / f'mahjong-web-{release}.tar.gz'
out.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(out, 'w:gz', compresslevel=1) as tar:
    for path in sorted(files):
        tar.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    for name, data in [('release-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode()), ('source-changes.patch', patch)]:
        info = tarfile.TarInfo(name)
        info.size, info.mode = len(data), 0o644
        tar.addfile(info, io.BytesIO(data))
with out.open('rb') as stream:
    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
out.with_suffix('.gz.sha256').write_text(f'{sha}  {out.name}\n')
print(json.dumps({'archive': str(out), 'release': release, 'sha256': sha, 'files': len(files)}), flush=True)
