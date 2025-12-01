#!/usr/bin/env python3
"""Check if all used packages are in requirements.txt - filtered version"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# Standard library modules (Python 3.10+) - expanded list
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
    'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zoneinfo', '_thread',
    'zlib', 'ntpath', 'opcode', 'setuptools', 'pip', 'pkg_resources'
}

# Local/project modules
LOCAL_MODULES = {'odoo', 'addons', 'setup'}

# Package name mappings (import name -> package name in requirements.txt)
PACKAGE_MAPPINGS = {
    'PIL': 'pillow',
    'OpenSSL': 'pyopenssl',
    'serial': 'pyserial',
    'magic': 'python_magic',
    'ldap': 'python_ldap',
    'stdnum': 'python_stdnum',
    'dateutil': 'python_dateutil',
    'jwt': 'pyjwt',
    'slugify': 'python_slugify',
    'bs4': 'beautifulsoup4',
    'sass': 'libsass',
}

# Known optional/dev dependencies (not critical for core functionality)
OPTIONAL_DEPS = {
    'IPython', 'bpython', 'ptpython',  # Alternative shells
    'astroid', 'pylint',  # Linting tools
    'watchdog',  # File watching (dev feature)
    'pexpect',  # Testing tool
    'aiortc',  # IoT specific
    'aiosmtpd',  # Testing SMTP server
    'ansitoimg',  # Internal tool
}

# Platform-specific packages
PLATFORM_SPECIFIC = {
    'win32api', 'win32com', 'win32print', 'win32service', 'win32serviceutil',  # Windows
    'pywintypes',  # Windows
    'dbus', 'evdev', 'inotify', 'pyudev', 'cups', 'usb',  # Linux
}

# Vendor dependencies (bundled/vendored)
VENDORED = {
    'openerp',  # Legacy Odoo name
    '_typeshed',  # Type stub
}

def extract_package_name(import_line):
    """Extract the base package name from an import statement"""
    # Match "import package" or "from package import ..."
    match = re.match(r'^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))', import_line)
    if match:
        package = match.group(1) or match.group(2)
        # Get the top-level package
        top_package = package.split('.')[0]

        # Filter out invalid package names (likely from comments/strings)
        if top_package and top_package[0].isupper() and len(top_package) < 20:
            # Check if it looks like a real package name
            if re.match(r'^[A-Z][a-zA-Z0-9_]*$', top_package):
                return top_package
        elif top_package and top_package[0].islower():
            return top_package
    return None

def is_third_party(package):
    """Check if a package is third-party (not stdlib or local)"""
    if not package:
        return False
    if package in STDLIB_MODULES:
        return False
    if package in LOCAL_MODULES:
        return False
    # Filter out common English words that are false positives
    common_words = {'a', 'an', 'the', 'that', 'this', 'there', 'which', 'any',
                    'another', 'different', 'multiple', 'something', 'somethingElse',
                    'directly', 'system', 'does', 'isn', 'its', 'nary', 'parent',
                    'partner', 'purchase', 'sales', 'mail', 'mailing', 'vendors',
                    'module_name', 'event_sale', 'hr_employee', 'hr_leave',
                    'hr_leave_allocation', 'talent_pool_applicants', 'record_portal_url_auth',
                    'ir_model_data', 'm2o', 'c', 'd'}
    if package.lower() in common_words:
        return False
    # Filter out test class names
    if package.startswith('Line') or package.startswith('Default'):
        return False
    # Filter out obviously wrong names
    if len(package) == 1:
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
                                                  '.tox', '.eggs', '*.egg-info', '_vendor',
                                                  'migrations'}]

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
                    # Skip comments
                    if line.strip().startswith('#'):
                        continue

                    package = extract_package_name(line)
                    if package and is_third_party(package):
                        rel_path = os.path.relpath(py_file, directory)
                        imports[package].add(f"{rel_path}:{line_num}")
        except Exception as e:
            print(f"Error reading {py_file}: {e}", file=sys.stderr)

    return imports

def categorize_missing(package):
    """Categorize a missing package"""
    if package in OPTIONAL_DEPS:
        return 'optional'
    if package in PLATFORM_SPECIFIC:
        return 'platform'
    if package in VENDORED:
        return 'vendored'
    return 'required'

def main():
    project_root = Path(__file__).parent
    requirements_file = project_root / 'requirements.txt'

    print("=" * 80)
    print("DEPENDENCY ANALYSIS (Filtered)")
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
        # Check with mapping
        check_name = PACKAGE_MAPPINGS.get(package, package)
        package_normalized = check_name.lower().replace('-', '_')

        if (check_name.lower() not in req_packages and
            package_normalized not in req_packages):
            missing[package] = files

    # Categorize missing packages
    by_category = {'required': [], 'optional': [], 'platform': [], 'vendored': []}
    for package in missing.keys():
        category = categorize_missing(package)
        by_category[category].append(package)

    # Report results
    print("=" * 80)
    print(f"ANALYSIS RESULTS")
    print("=" * 80)
    print()

    if by_category['required']:
        print(f"⚠ MISSING REQUIRED PACKAGES ({len(by_category['required'])})")
        print("-" * 80)
        for package in sorted(by_category['required']):
            files = missing[package]
            print(f"\n  • {package}")
            print(f"    Used in {len(files)} location(s):")
            for file_loc in sorted(list(files)[:3]):
                print(f"      - {file_loc}")
            if len(files) > 3:
                print(f"      ... and {len(files) - 3} more")
        print()

    if by_category['optional']:
        print(f"ℹ OPTIONAL/DEV DEPENDENCIES ({len(by_category['optional'])})")
        print("-" * 80)
        print(f"  {', '.join(sorted(by_category['optional']))}")
        print()

    if by_category['platform']:
        print(f"ℹ PLATFORM-SPECIFIC PACKAGES ({len(by_category['platform'])})")
        print("-" * 80)
        print(f"  {', '.join(sorted(by_category['platform']))}")
        print()

    if not any(by_category.values()):
        print("✓ ALL CORE PACKAGES FOUND")
        print()
        print("All third-party packages used in the code are listed in requirements.txt")
        print()

    return 0 if not by_category['required'] else 1

if __name__ == '__main__':
    sys.exit(main())
