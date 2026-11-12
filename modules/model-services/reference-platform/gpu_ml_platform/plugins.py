"""Only administrator-installed device plugins are loaded at process startup."""
import importlib, os

def load_plugins():
    for name in filter(None, os.environ.get('MODEL_DEVICE_PLUGINS', '').split(',')):
        importlib.import_module(name.strip())
