# -*- coding: utf-8 -*-
"""统一配置加载：从 config/settings.json 读取，环境变量可覆盖。
本包与根目录 config.py 存在命名冲突，此处将根 config 逻辑导入并再导出。"""
import importlib.util
import os
_config_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.py')
if os.path.isfile(_config_py):
    _spec = importlib.util.spec_from_file_location('_config_root', _config_py)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    Config = _mod.Config
    DATA_DIR = _mod.DATA_DIR
    load_dotenv = _mod.load_dotenv
    get_jenkins_credentials = _mod.get_jenkins_credentials
    APK_SITE_ROOT = _mod.APK_SITE_ROOT
    JENKINS_CLONE_DIR = _mod.JENKINS_CLONE_DIR
    CONFIG_DIR = _mod.CONFIG_DIR
    __all__ = ['Config', 'DATA_DIR', 'load_dotenv', 'get_jenkins_credentials', 'APK_SITE_ROOT', 'JENKINS_CLONE_DIR', 'CONFIG_DIR']
