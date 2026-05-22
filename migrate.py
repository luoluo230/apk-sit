#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK 下载站 - 迁移工具
功能：打包所有文件、解压部署、备份恢复
"""

import os
import sys
import zipfile
import shutil
import argparse
from datetime import datetime

def pack(output_file='apk-site-backup.zip'):
    """打包所有文件"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    print(f"📦 打包 APK 下载站...")
    print(f"   源目录：{script_dir}")
    print(f"   目标文件：{output_file}")
    
    # 创建压缩包
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(script_dir):
            # 跳过不必要的目录
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'logs', 'venv']]
            
            for file in files:
                if file.endswith('.zip'):
                    continue
                    
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(script_dir))
                zipf.write(file_path, arcname)
                print(f"   ✓ {arcname}")
    
    print(f"\n✅ 打包完成：{output_file}")
    print(f"   大小：{os.path.getsize(output_file) / 1024 / 1024:.1f} MB")

def unpack(input_file, target_dir=None):
    """解压到指定目录"""
    if not os.path.exists(input_file):
        print(f"❌ 文件不存在：{input_file}")
        sys.exit(1)
    
    if target_dir is None:
        target_dir = os.path.join(os.path.dirname(input_file), 'apk-site')
    
    print(f"📥 解压 APK 下载站...")
    print(f"   源文件：{input_file}")
    print(f"   目标目录：{target_dir}")
    
    os.makedirs(target_dir, exist_ok=True)
    
    with zipfile.ZipFile(input_file, 'r') as zipf:
        zipf.extractall(target_dir)
    
    print(f"\n✅ 解压完成")
    print(f"   目录：{target_dir}")
    print(f"\n下一步:")
    print(f"   1. cd {target_dir}")
    print(f"   2. 编辑 config.env 修改配置")
    print(f"   3. 运行 ./deploy.sh (macOS/Linux) 或 deploy.bat (Windows)")

def backup(backup_dir=None):
    """备份到指定目录"""
    if backup_dir is None:
        backup_dir = f"apk-site-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    print(f"💾 备份 APK 下载站...")
    pack(os.path.join(backup_dir, 'backup.zip'))

def main():
    parser = argparse.ArgumentParser(description='APK 下载站迁移工具')
    parser.add_argument('action', choices=['pack', 'unpack', 'backup'], 
                        help='操作类型')
    parser.add_argument('--file', '-f', help='输入/输出文件名')
    parser.add_argument('--target', '-t', help='目标目录')
    
    args = parser.parse_args()
    
    if args.action == 'pack':
        pack(args.file or 'apk-site-backup.zip')
    elif args.action == 'unpack':
        if not args.file:
            print("❌ 请指定输入文件")
            sys.exit(1)
        unpack(args.file, args.target)
    elif args.action == 'backup':
        backup()

if __name__ == '__main__':
    main()
