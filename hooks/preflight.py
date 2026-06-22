#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import subprocess

def main():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    hookctl_path = os.path.join(dir_path, "hookctl.py")
    
    cmd = [sys.executable, hookctl_path, "preflight"] + sys.argv[1:]
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
