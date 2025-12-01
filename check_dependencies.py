#!/usr/bin/env python3
"""Check if all used packages are in requirements.txt"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# Standard library modules (Python 3.10+)
STDLIB_MODULES = {
    '__future__', 'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio',
    'asyncore', 'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect',
    'builtins', 'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code',
    'codecs', 'codeop', 'collections', 'colorsys', 'compileall', 'concurrent', 'configparser',
    'contextlib', 'contextvars', 'copy', 'copyreg', 'cProfile', 'crypt', 'csv', 'ctypes',
    'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'distutils',
    'doctest', 'email', 'encodings', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp',
    'fileinput', 'fnmatch', 'formatter', 'fractions', 'ftplib', 'functools', 'gc', 'getopt',
    'getpass', 'gettext', 'glob', 'graphlib', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac',
    'html', 'http', 'idlelib', 'imaplib', 'imghdr', 'imp', 'importlib', 'inspect', 'io',
    'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3', 'linecache', 'locale', 'logging',
    'lzma', 'mailbox', 'mailcap', 'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder',
    'msilib', 'msvcrt', 'multiprocessing', 'netrc', 'nis', 'nntplib', 'numbers', 'operator',
    'optparse', 'os', 'ossaudiodev', 'parser', 'pathlib', 'pdb', 'pickle', 'pickletools',
    'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 'posix', 'posixpath', 'pprint',
    'profile', 'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc', 'queue', 'quopri',
    'random', 're', 'readline', 'reprlib', 'resource', 'rlcompleter', 'runpy', 'sched',
    'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal', 'site',
    'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3', 'ssl',
    'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess', 'sunau', 'symbol',
    'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib', 'tempfile',
    'termios', 'test', 'textwrap', 'threading', 'time', 'timeit', 'tkinter', 'token',
    'tokenize', 'tomllib', 'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo',
    'types', 'typing', 'typing_extensions', 'unicodedata', 'unittest', 'urllib', 'uu', 'uuid',
    'venv', 'warnings', 'wave', 'weakref', 'webbrowser', 'winreg', 'winsound', 'wsgiref',
    'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zoneinfo', '_thread'
}

# Local/project modules
LOCAL_MODULES = {'odoo', 'addons', 'setup'}

def extract_package_name(import_line):
    """Extract the base package name from an import statement"""
    # Match "import package" or "from package import ..."
    match = re.match(r'^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))', import_line)
    if match:
        package = match.group(1) or match.group(2)
        # Get the top-level package
        return package.split('.')[0]
    return None

def is_third_party(package):
    """Check if a package is third-party (not stdlib or local)"""
    if not package:
        return False
    if package in STDLIB_MODULES:
        return False
    if package in LOCAL_MODULES:
        return False
    return True

def get_requirements_packages(requirements_file):
    """Extract package names from requirements.txt"""
    packages = set()

    if not os.path.exists(requirements_file):
        return packages

    with open(requirements_file, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            # Extract package name (before ==, >=, etc.)
            match = re.match(r'^([a-zA-Z0-9_-]+)', line)
            if match:
                package = match.group(1).lower().replace('-', '_')
                packages.add(package)
                # Also add the original format
                packages.add(match.group(1).lower())

    return packages

def find_python_files(directory):
    """Find all Python files in the directory"""
    for root, dirs, files in os.walk(directory):
        # Skip common non-essential directories
        dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', '.pytest_cache',
                                                  'node_modules', '.venv', 'venv', '.mypy_cache',
                                                  '.tox', '.eggs', '*.egg-info'}]

        for file in files:
            if file.endswith('.py'):
                yield os.path.join(root, file)

def analyze_imports(directory):
    """Analyze all imports in Python files"""
    imports = defaultdict(set)  # package -> set of files using it

    for py_file in find_python_files(directory):
        try:
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    package = extract_package_name(line)
                    if package and is_third_party(package):
                        rel_path = os.path.relpath(py_file, directory)
                        imports[package].add(f"{rel_path}:{line_num}")
        except Exception as e:
            print(f"Error reading {py_file}: {e}", file=sys.stderr)

    return imports

def main():
    project_root = Path(__file__).parent
    requirements_file = project_root / 'requirements.txt'

    print("=" * 80)
    print("DEPENDENCY ANALYSIS")
    print("=" * 80)
    print()

    # Get packages from requirements.txt
    req_packages = get_requirements_packages(requirements_file)
    print(f"Packages in requirements.txt: {len(req_packages)}")
    print()

    # Analyze imports
    print("Analyzing Python files...")
    used_packages = analyze_imports(project_root)
    print(f"Third-party packages found in code: {len(used_packages)}")
    print()

    # Find missing packages
    missing = {}
    for package, files in used_packages.items():
        package_normalized = package.lower().replace('-', '_')
        if (package.lower() not in req_packages and
            package_normalized not in req_packages):
            missing[package] = files

    # Report results
    if missing:
        print("=" * 80)
        print(f"MISSING PACKAGES ({len(missing)})")
        print("=" * 80)
        print()
        print("The following packages are used in the code but NOT in requirements.txt:")
        print()

        for package in sorted(missing.keys()):
            files = missing[package]
            print(f"  • {package}")
            print(f"    Used in {len(files)} location(s):")
            for file_loc in sorted(list(files)[:5]):  # Show max 5 locations
                print(f"      - {file_loc}")
            if len(files) > 5:
                print(f"      ... and {len(files) - 5} more location(s)")
            print()
    else:
        print("=" * 80)
        print("✓ ALL PACKAGES FOUND")
        print("=" * 80)
        print()
        print("All third-party packages used in the code are listed in requirements.txt")
        print()

    # Show summary of used packages
    print("=" * 80)
    print("USED THIRD-PARTY PACKAGES")
    print("=" * 80)
    print()
    for package in sorted(used_packages.keys()):
        status = "✓" if package.lower() in req_packages or package.lower().replace('-', '_') in req_packages else "✗"
        print(f"  {status} {package}")
    print()

    return 0 if not missing else 1

if __name__ == '__main__':
    sys.exit(main())
