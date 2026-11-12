#!/usr/bin/env python3
"""Validate module ownership, frozen payloads, links, mounts and script syntax."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main():
    registry = json.loads((ROOT / 'modules/layout-migration.json').read_text())
    paths = registry['paths']
    for old, new in paths.items():
        assert (ROOT / new).is_file(), f'Missing relocated asset: {old} -> {new}'
    for old, digest in registry['immutable_sha256'].items():
        path = ROOT / paths.get(old, old)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'Frozen payload changed: {path}'
    aliases = [p for p in (ROOT / 'modules').rglob('*') if p.is_symlink()]
    for path in aliases:
        assert path.exists(), f'Broken compatibility view: {path}'
        assert path.resolve().is_relative_to(ROOT / 'modules/devices/nvidia-gpu/common'), path
    assert len(aliases) == 10, f'Unexpected compatibility view count: {len(aliases)}'
    missing = []
    for parent in ['modules', 'docs', 'deploy']:
        for path in (ROOT / parent).rglob('*.md'):
            if path.is_symlink():
                continue
            for raw in re.findall(r'\]\(([^)]+)\)', path.read_text()):
                target = raw.strip('<>')
                if '://' in target or target.startswith(('#', 'mailto:', 'plugin:', 'app:')):
                    continue
                target = unquote(target.split('#')[0])
                # Preserve explicitly external temporary source locations in research notes.
                if target.startswith('/') and not target.startswith(str(ROOT) + '/'):
                    continue
                resolved = Path(target) if target.startswith('/') else path.parent / target
                if not resolved.exists():
                    missing.append((str(path.relative_to(ROOT)), raw))
    assert not missing, 'Broken Markdown links:\n' + '\n'.join(f'{p}: {link}' for p, link in missing)
    for path in (ROOT / 'modules').rglob('*.py'):
        compile(path.read_text(), str(path), 'exec')
    for path in [*(ROOT / 'modules').rglob('*.sh'), *(ROOT / 'scripts').glob('*.sh')]:
        subprocess.run(['bash', '-n', str(path)], check=True)
    # Resolve host bind sources without requiring PyYAML or access to Docker.
    mounts = 0
    for rel in ['deploy/nvidia-gpu/lab/compose.yaml', 'deploy/nvidia-gpu/review/compose.yaml', 'deploy/nvidia-gpu/ml/compose.yaml', 'deploy/shared/compose.yaml', 'deploy/model-platform/compose.yaml']:
        path = ROOT / rel
        for line in path.read_text().splitlines():
            match = re.match(r'\s*- (\.\.?/[^:]+):', line)
            if match:
                source = (path.parent / match[1]).resolve()
                assert source.exists(), f'Missing bind source: {source}'
                mounts += 1
            match = re.match(r'\s*context:\s*(\.\.?/\S+)', line)
            if match:
                context = (path.parent / match[1]).resolve()
                assert context.is_dir(), line
                if context != ROOT:
                    assert (context / 'Dockerfile').is_file(), line
    # Shared cores cannot silently acquire vendor imports. Historical pickle shims
    # in runtime/models.py and dcgm_scenarios.py are explicit compatibility exceptions.
    shared = [ROOT/'modules/platform', ROOT/'modules/model-services/contracts',
              ROOT/'modules/model-services/adapters']
    shared_files = [p for base in shared for p in base.rglob('*.py')]
    shared_files += [ROOT/'modules/model-services/runtime/gpu_ml_runtime'/name
                     for name in ('pipeline.py','detectors.py','evaluation.py','catalog.py')]
    for path in shared_files:
        import ast
        for node in ast.walk(ast.parse(path.read_text())):
            names = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                     [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            assert not any(n.split('.')[0] in ('gpu_ml','nvidia_gpu_ml') for n in names), path
    for rel in ('modules/devices/nvidia-gpu/README.md','modules/devices/huawei-npu/README.md'):
        assert (ROOT/rel).is_file(), f'Missing device entry: {rel}'
    assert not any((ROOT / p).exists() for p in ['monitoring', 'lab', 'rules', 'tests', 'reports', 'research_notes']), 'Old implementation directory remains at root'
    print(f'PASS: {len(paths)} relocated assets, {len(registry["immutable_sha256"])} frozen payloads, '
          f'{len(aliases)} common views, {mounts} bind sources, Markdown and script syntax')


if __name__ == '__main__':
    try:
        main()
    except (AssertionError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        sys.exit(1)
