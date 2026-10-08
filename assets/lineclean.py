import os
import sys
import argparse
import subprocess
import codecs

# The file extensions we are authorized to process (case-insensitive)
TARGET_EXTS = {'.py', '.toml', '.json', '.md', '.txt'}

def get_git_root():
    """Finds the root directory of the current git repository."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_git_modified_files(git_root):
    """
    Returns the union of tracked unstaged changes, tracked staged changes,
    and untracked files. This matches the documented "uncommitted files"
    behavior without relying on last-run timestamps.
    """
    commands = (
        ['git', 'diff', '--name-only', '--diff-filter=ACMR'],
        ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
        ['git', 'ls-files', '--others', '--exclude-standard'],
    )

    files = set()
    for command in commands:
        try:
            result = subprocess.run(
                command,
                cwd=git_root,
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError:
            print("[!] Error running git commands. Make sure git is installed and available.")
            return []

        for relative_path in result.stdout.splitlines():
            if not relative_path:
                continue

            absolute_path = os.path.join(git_root, relative_path)
            if os.path.isfile(absolute_path):
                files.add(os.path.normpath(absolute_path))

    return sorted(files)

def process_file(filepath, dry_run=False):
    """
    Reads a file, removes trailing whitespace, standardizes to CRLF,
    and saves it if modifications are necessary.
    """
    try:
        with open(filepath, 'rb') as f:
            original_bytes = f.read()

        if not original_bytes:
            return False # File is entirely empty, nothing to do

        # Handle Byte Order Mark (BOM) prevalent in Windows/C# environments
        bom = b''
        content_bytes = original_bytes
        if content_bytes.startswith(codecs.BOM_UTF8):
            bom = codecs.BOM_UTF8
            content_bytes = content_bytes[3:]

        # Decode text safely
        try:
            text = content_bytes.decode('utf-8')
            write_encoding = 'utf-8'
        except UnicodeDecodeError:
            # Fallback for unexpected legacy encodings
            text = content_bytes.decode('latin-1')
            write_encoding = 'latin-1'

        # Split lines natively dealing with \r\n, \n, or \r
        lines = text.splitlines()

        # rstrip(" \t") only removes space and tab, preserving layout formatting otherwise
        cleaned_lines = [line.rstrip(" \t") for line in lines]

        # Re-join strictly with Windows line endings
        new_text = "\r\n".join(cleaned_lines)

        # Restore trailing newline if the original text had one
        if text.endswith(('\n', '\r')):
            new_text += "\r\n"

        # Reconstruct exactly what would be written to disk
        new_bytes = bom + new_text.encode(write_encoding)

        # Byte-level check to avoid unnecessary I/O writes and file mtime updates
        if new_bytes == original_bytes:
            return False

        if dry_run:
            print(f"[DRY RUN] Would clean: {filepath}")
            return True

        # Perform the actual write
        with open(filepath, 'wb') as f:
            f.write(new_bytes)
        print(f"[CLEANED] {filepath}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to process {filepath}: {e}")
        return False

def mode_git_tracking(dry_run):
    """Mode 1: Process all eligible uncommitted files in the current git repo."""
    git_root = get_git_root()
    if not git_root:
        print("[!] Not in a git repository. Cannot run default Git tracking mode.")
        sys.exit(1)

    print(f"[*] Running in Mode 1 (Git tracking). Git Root: {git_root}")
    print("[*] Processing all eligible uncommitted files.")

    files_to_check = get_git_modified_files(git_root)
    processed_count = 0
    scanned_count = 0

    for filepath in files_to_check:
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in TARGET_EXTS:
            continue

        scanned_count += 1
        if process_file(filepath, dry_run):
            processed_count += 1

    print(f"[*] Mode 1 complete. Evaluated {scanned_count} files, cleaned {processed_count}.")

def mode_single_file(filepath, dry_run):
    """Mode 2: Process a single targeted file path."""
    if not os.path.isfile(filepath):
        print(f"[!] File not found: {filepath}")
        sys.exit(1)

    print(f"[*] Running in Mode 2 (Single File)")
    if process_file(filepath, dry_run):
        print("[*] Mode 2 complete. File cleaned.")
    else:
        print("[*] Mode 2 complete. File was already clean or skipped.")

def mode_directory(dirpath, dry_run):
    """Mode 3: Recursively find and process matching file extensions."""
    if not os.path.isdir(dirpath):
        print(f"[!] Directory not found: {dirpath}")
        sys.exit(1)

    print(f"[*] Running in Mode 3 (Directory Scan)")
    processed_count = 0
    scanned_count = 0

    for root, _, files in os.walk(dirpath):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext in TARGET_EXTS:
                scanned_count += 1
                filepath = os.path.join(root, filename)
                if process_file(filepath, dry_run):
                    processed_count += 1

    print(f"[*] Mode 3 complete. Evaluated {scanned_count} valid files, cleaned {processed_count}.")

def main():
    parser = argparse.ArgumentParser(description="Formatter script to trim trailing whitespace and enforce CRLF.")
    parser.add_argument("target", nargs="?", default=None,
                        help="Optional. File or directory to process. If omitted, runs in Default Mode (Git tracking).")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Dry run mode. Shows output without modifying files or saving the last run time.")

    args = parser.parse_args()

    if args.debug:
        print("========== DRY RUN MODE ACTIVE ==========")

    if args.target:
        target_path = os.path.abspath(args.target)
        if os.path.isdir(target_path):
            mode_directory(target_path, args.debug)
        elif os.path.isfile(target_path):
            mode_single_file(target_path, args.debug)
        else:
            print(f"[!] Target path does not exist: {target_path}")
            sys.exit(1)
    else:
        mode_git_tracking(args.debug)

if __name__ == "__main__":
    main()
