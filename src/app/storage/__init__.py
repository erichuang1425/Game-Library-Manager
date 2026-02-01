from importlib import import_module

from .paths import library_json_path, settings_json_path, temp_data_dir, paths_diag, get_app_dir

__all__ = [
    "library_json_path",
    "settings_json_path",
    "temp_data_dir",
    "paths_diag",
    "get_app_dir",
    "load_library",
    "save_library",
    "load_settings",
    "save_settings",
    "load_library_bundle",
    "save_library_bundle",
]


def __getattr__(name):
    if name in {
        "load_library",
        "save_library",
        "load_settings",
        "save_settings",
        "load_library_bundle",
        "save_library_bundle",
    }:
        mod = import_module(".json_store", __name__)
        return getattr(mod, name)
    raise AttributeError(name)
