# sitecustomize.py
import sys
import types

# создаём фейковый модуль aiogram.utils.executor
executor_module = types.ModuleType("aiogram.utils.executor")

# регистрируем его в sys.modules
sys.modules["aiogram.utils.executor"] = executor_module
