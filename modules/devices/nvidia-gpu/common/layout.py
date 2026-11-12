"""Resolve archived asset locations and keep generated documentation relocatable.

The registry preserves historical evidence verbatim; it is not a runtime alias for
GPU metrics or an alternate rule configuration source.
"""
import json
import os
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote

REPOSITORY = Path(__file__).resolve().parents[4]
REGISTRY = REPOSITORY / 'modules/layout-migration.json'
PATHS = json.loads(REGISTRY.read_text())['paths']
_COMMAND_PATHS = {k: v for k, v in PATHS.items() if k.endswith(('.py', '.sh', '.mjs'))}
_COMMAND_PATTERN = re.compile(r'(?<![\w/.-])(' + '|'.join(re.escape(k) for k in sorted(_COMMAND_PATHS, key=len, reverse=True)) + r')(?![\w/.-])')


def canonical_path(legacy_path):
    """Return the single canonical file location for a historical repo path."""
    key = Path(legacy_path).as_posix()
    if key in PATHS:
        return REPOSITORY / PATHS[key]
    directories = dict(json.loads(REGISTRY.read_text()).get('directory_aliases', {}))
    directories.update({
        'monitoring/hardware': 'modules/devices/nvidia-gpu/common/monitoring/hardware',
        'monitoring/metrics': 'modules/devices/nvidia-gpu/common/monitoring/metrics',
        'monitoring': 'modules/devices/nvidia-gpu/rules/monitoring',
        'lab/anomaly_demo': 'modules/devices/nvidia-gpu/ml/demo',
        'lab': 'modules/devices/nvidia-gpu/rules/lab',
        'rules': 'modules/devices/nvidia-gpu/rules/rules',
        'tests': 'modules/devices/nvidia-gpu/rules/tests',
        'scripts': 'modules/devices/nvidia-gpu/rules/scripts',
        'reports/demos/anomaly': 'modules/devices/nvidia-gpu/ml/evidence/anomaly',
        'reports/demos/h100': 'modules/devices/nvidia-gpu/rules/reports/demos/h100',
    })
    for old, new in sorted(directories.items(), key=lambda item: len(item[0]), reverse=True):
        if key == old or key.startswith(old + '/'):
            return REPOSITORY / new / key[len(old):].lstrip('/')
    return REPOSITORY / key


def relocate_markdown(content, legacy_document):
    """Rebase legacy Markdown links and runnable command examples to new owners."""
    old_document = Path(legacy_document).as_posix()
    new_document = canonical_path(old_document)

    def replace(match):
        raw = match.group(1)
        target = raw.strip('<>')
        if '://' in target or target.startswith(('#', 'mailto:', 'plugin:', 'app:')):
            return match.group(0)
        path, sep, fragment = target.partition('#')
        path = unquote(path)
        absolute = path.startswith(str(REPOSITORY) + '/')
        if absolute:
            key = path[len(str(REPOSITORY)) + 1:]
        elif path.startswith('/'):
            return match.group(0)
        else:
            key = posixpath.normpath(posixpath.join(posixpath.dirname(old_document), path))
        old_target = REPOSITORY / key
        new_target = canonical_path(key)
        if key not in PATHS and not old_target.exists() and not new_target.exists():
            # Preserve unresolved pre-existing external artifacts for the checker.
            return match.group(0)
        replacement = str(new_target) if absolute else os.path.relpath(new_target, new_document.parent)
        if sep:
            replacement += '#' + fragment
        if raw.startswith('<') or ' ' in replacement:
            replacement = '<' + replacement + '>'
        return '](' + replacement + ')'

    content = re.sub(r'\]\(([^)]+)\)', replace, content)
    return _COMMAND_PATTERN.sub(lambda m: _COMMAND_PATHS[m.group(1)], content)
