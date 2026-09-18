"""Create a portable submission archive without credentials, caches or runtime files."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from app.config import ROOT

EXCLUDED = {'.git', '.cache', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', 'runs'}


def main():
    target = ROOT.parent / 'Aptino_Submission.zip'
    files = []
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in EXCLUDED for part in relative.parts):
            continue
        if path.name.startswith('.env') and path.name != '.env.example':
            continue
        if path.suffix in {'.pyc', '.log', '.zip'}:
            continue
        files.append(path)
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(Path('aptino-claim-engine') / path.relative_to(ROOT)))
    manifest = {
        'archive': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'file_count': len(files), 'files': [str(p.relative_to(ROOT)).replace('\\', '/') for p in files],
        'excluded': ['.env and credentials', 'model caches', 'virtual environments', 'git internals', 'scratch runs'],
    }
    (ROOT.parent / 'Submission_Manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Created {target.name}: {len(files)} files, {target.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
