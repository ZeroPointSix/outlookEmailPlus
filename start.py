#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动脚本 - 加载环境变量并启动 Flask 应用
"""
import os
import sys
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 确保环境变量已加载
if not os.getenv('SECRET_KEY'):
    print("错误：SECRET_KEY 环境变量未设置")
    sys.exit(1)

# 直接运行 web_outlook_app.py
if __name__ == '__main__':
    # 使用 exec 运行 web_outlook_app.py，保持 __name__ == "__main__"
    with open('web_outlook_app.py', 'r', encoding='utf-8') as f:
        code = f.read()
    exec(code, {'__name__': '__main__', '__file__': 'web_outlook_app.py'})

