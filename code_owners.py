#!/usr/bin/env python3
import os
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# === CONFIG: tweak these for your setup ======================================

# Paths that should be *skipped* if they appear in the repo-relative path
SKIP_PATH_SUBSTRINGS = [
    "/node_modules/",
    "/.venv/",
    "/venv/",
    "/dist/",
    "/build/",
    "/.git/",
    "/.mypy_cache/",
    "/__pycache__/",
    "/.pytest_cache/",
]

# Max file size in bytes; larger files are skipped (to avoid pathological cases)
MAX_FILE_SIZE = 1_000_000  # 1 MB; bump if needed

# Extra args to git blame. Add -M -C if you want it to follow moves/copies,
# but that will slow things down.
BLAME_EXTRA_ARGS = ["-w"]  # ignore whitespace

# Number of worker threads to run git blame in parallel
NUM_WORKERS = max(os.cpu_count() or 4, 4)

# Email domains that you consider INTERNAL.
# <<< EDIT THIS for your company >>>
INTERNAL_DOMAINS = {
    # "your-company.org",
    # "another-internal-domain.org",
}

# Author names/emails to ignore completely (bots, etc.)
IGNORE_EMAILS = {
    "dependabot[bot]@users.noreply.github.com",
}
IGNORE_NAMES = {
    "Dependabot",
}

# How many authors to show in the global breakdown
TOP_N_AUTHORS = 100

# How many authors to show per file extension
TOP_N_AUTHORS_PER_EXT = 5

# ============================================================================


def run_git(args, cwd=None):
    """Run a git command and return stdout as text, or raise on error."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def is_git_repo():
    try:
        out = run_git(["rev-parse", "--is-inside-work-tree"])
        return out.strip() == "true"
    except Exception:
        return False


def list_files():
    """Return a list of repo-relative file paths tracked by git (with filters)."""
    out = run_git(["ls-files"])
    files = out.strip().splitlines()
    filtered = []
    for path in files:
        # Normalize
        path = path.strip()
        if not path:
            continue

        # Skip unwanted paths by substring
        # prefix with "/" so substrings like "/node_modules/" match cleanly
        full = f"/{path}"
        if any(s in full for s in SKIP_PATH_SUBSTRINGS):
            continue

        # Skip huge files
        try:
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE:
                continue
        except OSError:
            # If we can't stat it, just skip
            continue

        filtered.append(path)

    return filtered


def classify_email(email: str):
    """Return 'internal', 'external', or 'unknown' based on email domain."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return "unknown"
    domain = email.split("@", 1)[1]
    if domain in INTERNAL_DOMAINS:
        return "internal"
    return "external"


def blame_file(path: str):
    """
    Run git blame --line-porcelain on a file and return:
    - counts: Counter of key (email or name) -> line count
    - names: mapping email -> name (best effort)
    """
    args = ["blame", "--line-porcelain"] + BLAME_EXTRA_ARGS + ["HEAD", "--", path]
    try:
        out = run_git(args)
    except RuntimeError as e:
        print(f"[WARN] Skipping {path}: {e}")
        return Counter(), {}

    counts = Counter()
    email_to_name = {}

    current_author = None
    current_email = None

    for line in out.splitlines():
        if line.startswith("author "):
            current_author = line[len("author ") :].strip()
        elif line.startswith("author-mail "):
            raw = line[len("author-mail ") :].strip()
            # author-mail is like <email>; strip <>
            if raw.startswith("<") and raw.endswith(">"):
                raw = raw[1:-1]
            current_email = raw
        elif line.startswith("\t"):
            # Actual line of code
            name = current_author or ""
            email = current_email or ""

            if email in IGNORE_EMAILS or name in IGNORE_NAMES:
                continue

            key = email if email else name if name else "UNKNOWN"
            counts[key] += 1

            if email and name and email not in email_to_name:
                email_to_name[email] = name

    return counts, email_to_name


def get_extension(path: str) -> str:
    """Return normalized file extension (e.g. '.py'), or '<no_ext>'."""
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    return ext if ext else "<no_ext>"


def main():  # noqa: C901
    if not is_git_repo():
        print("Error: this script must be run inside a git repository.")
        return

    print("Listing files...")
    files = list_files()
    if not files:
        print("No files found after filtering. Check SKIP_PATH_SUBSTRINGS / MAX_FILE_SIZE.")
        return

    print(f"Found {len(files)} files to analyze.")
    print(f"Running git blame in parallel with {NUM_WORKERS} workers...")

    global_counts = Counter()  # all files combined
    global_names = {}  # email -> name
    ext_counts = defaultdict(Counter)  # ext -> Counter(key -> lines)

    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        future_to_path = {executor.submit(blame_file, path): path for path in files}
        for idx, future in enumerate(as_completed(future_to_path), start=1):
            path = future_to_path[future]
            try:
                counts, names = future.result()
            except Exception as e:
                print(f"[ERROR] Exception while processing {path}: {e}")
                continue

            if not counts:
                continue

            # Global aggregation
            global_counts.update(counts)
            for email, name in names.items():
                global_names.setdefault(email, name)

            # Extension-based aggregation
            ext = get_extension(path)
            ext_counts[ext].update(counts)

            if idx % 100 == 0:
                print(f"  Processed {idx}/{len(files)} files...")

    if not global_counts:
        print("No blame data collected. Something is off (empty repo? all files skipped?).")
        return

    # === Global summary ======================================================
    internal_total = 0
    external_total = 0
    unknown_total = 0

    for key, count in global_counts.items():
        if "@" in key:
            cls = classify_email(key)
        else:
            cls = "unknown"

        if cls == "internal":
            internal_total += count
        elif cls == "external":
            external_total += count
        else:
            unknown_total += count

    total_lines = internal_total + external_total + unknown_total

    print("\n=== GLOBAL SUMMARY (current HEAD, by last author of each line) ===")
    print(f"Total lines considered: {total_lines}")
    if total_lines > 0:

        def pct(x):
            return f"{100.0 * x / total_lines:5.1f}%"

        print(f"  Internal: {internal_total:10d}  ({pct(internal_total)})")
        print(f"  External: {external_total:10d}  ({pct(external_total)})")
        print(f"  Unknown : {unknown_total:10d}  ({pct(unknown_total)})")

    print(f"\nTop {TOP_N_AUTHORS} authors by line ownership:\n")
    print(f"{'Lines':>10}  {'Class':>8}  {'Author':<30}  Email")
    print("-" * 80)

    for key, count in global_counts.most_common(TOP_N_AUTHORS):
        if "@" in key:
            email = key
            name = global_names.get(email, "")
        else:
            email = ""
            name = key

        cls = classify_email(email) if "@" in key else "unknown"
        display_name = (name or "").strip()
        if len(display_name) > 28:
            display_name = display_name[:27] + "…"

        print(f"{count:10d}  {cls:>8}  {display_name:<30}  {email}")

    # === Breakdown by file extension ========================================
    print("\n=== BREAKDOWN BY FILE TYPE (extension) ===\n")
    print(f"{'Ext':<10}  {'Lines':>10}  {'Internal':>10}  {'External':>10}  {'Unknown':>10}")
    print("-" * 60)

    # Sort extensions by total lines descending
    ext_order = sorted(
        ext_counts.items(),
        key=lambda kv: sum(kv[1].values()),
        reverse=True,
    )

    for ext, counts in ext_order:
        ext_internal = ext_external = ext_unknown = 0

        for key, cnt in counts.items():
            if "@" in key:
                cls = classify_email(key)
            else:
                cls = "unknown"

            if cls == "internal":
                ext_internal += cnt
            elif cls == "external":
                ext_external += cnt
            else:
                ext_unknown += cnt

        ext_total = ext_internal + ext_external + ext_unknown
        print(f"{ext:<10}  {ext_total:10d}  {ext_internal:10d}  {ext_external:10d}  {ext_unknown:10d}")

    # Optional: per-extension top authors
    print("\n=== TOP AUTHORS PER FILE TYPE ===\n")
    for ext, counts in ext_order:
        ext_total = sum(counts.values())
        if ext_total == 0:
            continue

        print(f"[{ext}] total lines: {ext_total}")
        print(f"{'Lines':>10}  {'Class':>8}  {'Author':<30}  Email")

        top_authors = counts.most_common(TOP_N_AUTHORS_PER_EXT)
        for key, cnt in top_authors:
            if "@" in key:
                email = key
                name = global_names.get(email, "")
            else:
                email = ""
                name = key

            cls = classify_email(email) if "@" in key else "unknown"
            display_name = (name or "").strip()
            if len(display_name) > 28:
                display_name = display_name[:27] + "…"

            print(f"{cnt:10d}  {cls:>8}  {display_name:<30}  {email}")
        print("")

    print("Done.")


if __name__ == "__main__":
    main()
