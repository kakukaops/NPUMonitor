"""Installed schema/model registry; no device defaults and no dynamic user code."""
TEMPLATES = {}
LEGACY_TYPES = []
LEGACY_BUILDERS = []

def legacy_model(template, algorithm):
    if not LEGACY_BUILDERS:
        raise ValueError('未安装对应设备的历史模型适配器')
    return LEGACY_BUILDERS[0](template, algorithm)
