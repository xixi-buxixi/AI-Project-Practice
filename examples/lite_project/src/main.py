#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

def fibonacci(n):
    if n <= 0:
        raise ValueError("N must be a positive integer.")
    if n == 1:
        return [0]
    
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq[:n]

def run_tests():
    # Simple self-test code
    try:
        assert fibonacci(1) == [0], "Test case 1 failed"
        assert fibonacci(2) == [0, 1], "Test case 2 failed"
        assert fibonacci(5) == [0, 1, 1, 2, 3], "Test case 3 failed"
        
        try:
            fibonacci(0)
            assert False, "Should raise ValueError for 0"
        except ValueError:
            pass
            
        print("ALL TESTS PASSED")
        sys.exit(0)
    except AssertionError as ae:
        print(f"TEST FAILED: {ae}", file=sys.stderr)
        sys.exit(1)

def main():
    if "--test" in sys.argv:
        run_tests()
        
    n = 5
    if "--n" in sys.argv:
        try:
            idx = sys.argv.index("--n")
            n = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            print("Invalid arguments. Use --n <integer>", file=sys.stderr)
            sys.exit(1)
            
    try:
        result = fibonacci(n)
        print(result)
        sys.exit(0)
    except ValueError as ve:
        print(f"Error: {ve}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
