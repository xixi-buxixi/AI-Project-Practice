#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import subprocess

def main():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    hookctl_path = os.path.join(dir_path, "hookctl.py")
    
    # Run finalize with --lite flag
    args = sys.argv[1:]
    if "--lite" not in args:
        args.append("--lite")
        
    cmd = [sys.executable, hookctl_path, "finalize"] + args
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
