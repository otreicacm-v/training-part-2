#!/usr/bin/env python3
"""
Translation Agent using Codex CLI

Autonomous translation script that uses Codex's non-interactive CLI (codex exec)
to translate Odoo project modules with full codebase context awareness.

Prerequisites:
    # Install Codex CLI
    # Follow instructions at https://codex.com/docs/cli

    # Ensure Codex is authenticated
    codex login

Usage:
    # Translate a single module
    ./scripts/translate_agent.py --module trn_vocabulary --lang fr

    # Translate with dependencies
    ./scripts/translate_agent.py --module trn_vocabulary --lang fr --with-deps

    # Skip POT update (assume already updated)
    ./scripts/translate_agent.py --module trn_vocabulary --lang fr --skip-pot-update

    # Dry run (check status only)
    ./scripts/translate_agent.py --module trn_vocabulary --lang fr --dry-run

Target Languages:
    - fr: French (primary)
    - es: Spanish
    - ar: Arabic (RTL support)
    - lo: Lao
"""

import argparse
import logging
import shutil
import subprocess
import sys
from pathlib import Path

# Import reusable components from translate_verify.py
# We'll import these functions directly
try:
    # Add parent directory to path to import from translate_verify
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from translate_verify import (
        LANGUAGES,
        get_po_file,
        get_pot_file,
        parse_po_file,
    )
except ImportError as e:
    print(f"Error importing from translate_verify.py: {e}")
    print("Make sure translate_verify.py is in the same directory")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
_logger = logging.getLogger(__name__)

# Get project root (script is at: odoo/custom/src/project_modules/scripts/translate_agent.py)
# Go up: scripts -> project_modules -> src -> custom -> odoo -> root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent
SRC_PATH = PROJECT_ROOT / "odoo" / "custom" / "src"


def _expand_modules_with_deps(modules_csv: str) -> str:
    """Return CSV of modules plus all their dependencies using manifestoo.

    Reuses pattern from tasks.py
    """
    if not modules_csv:
        return modules_csv

    manifestoo_cmd = shutil.which("manifestoo")
    use_docker_manifestoo = False
    if not manifestoo_cmd:
        # Try the doodba odoo container, which ships with manifestoo
        use_docker_manifestoo = True

    addons_dirs = [
        SRC_PATH / "project_modules",
        SRC_PATH / "odoo" / "addons",
    ]

    addons_path = (
        "/opt/odoo/custom/src/project_modules,/opt/odoo/custom/src/odoo/addons"
        if use_docker_manifestoo
        else f"{addons_dirs[0]},{addons_dirs[1]}"
    )
    base_cmd = [
        "manifestoo",
        "--odoo-series",
        "19.0",
        "--addons-path",
        addons_path,
        "--select-include",
        modules_csv,
        "list-depends",
        "--transitive",
        "--include-selected",
        "--separator",
        ",",
        "--ignore-missing",
    ]

    if use_docker_manifestoo:
        # Try to get docker compose command
        docker_compose_cmd = shutil.which("docker-compose") or "docker compose"
        cmd = [
            *docker_compose_cmd.split(),
            "run",
            "--rm",
            "odoo",
            *base_cmd,
        ]
    else:
        cmd = [manifestoo_cmd, *base_cmd[1:]]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        expanded = result.stdout.strip().splitlines()[-1]
        _logger.info("Expanded modules with dependencies: %s", expanded)
        return expanded
    except subprocess.CalledProcessError as exc:
        _logger.warning("manifestoo failed (%s); using original list", exc)
        return modules_csv
    except FileNotFoundError:
        _logger.warning("manifestoo not found; using original list")
        return modules_csv


def ensure_pot_updated(modules: list[str], database: str = "devel") -> bool:
    """Call invoke update-pot task to ensure POT files are up to date.

    Args:
        modules: List of module names to update
        database: Database name to use

    Returns:
        True if successful, False otherwise
    """
    _logger.info("Updating POT files for modules: %s", ", ".join(modules))

    # Build invoke command
    modules_csv = ",".join(modules)
    cmd = [
        "invoke",
        "update-pot",
        "--modules",
        modules_csv,
        "--database",
        database,
        "--msgmerge",
    ]

    try:
        subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        _logger.info("POT files updated successfully")
        return True
    except subprocess.CalledProcessError as e:
        _logger.error("Failed to update POT files: %s", e.stderr)
        return False
    except FileNotFoundError:
        _logger.error("invoke command not found. Make sure invoke is installed.")
        return False


def check_translation_status(pot_file: Path, po_file: Path) -> tuple[int, int, int]:
    """Check translation status by counting strings.

    Args:
        pot_file: Path to POT file
        po_file: Path to PO file

    Returns:
        Tuple of (total, translated, untranslated)
    """
    if not pot_file.exists():
        _logger.warning("POT file not found: %s", pot_file)
        return (0, 0, 0)

    # Parse POT file
    pot_entries = parse_po_file(pot_file)
    total = sum(1 for e in pot_entries if not e.is_header and e.msgid)

    if not po_file.exists():
        _logger.info("PO file does not exist yet: %s", po_file)
        return (total, 0, total)

    # Parse PO file
    po_entries = parse_po_file(po_file)
    translations = {e.msgid: e for e in po_entries if not e.is_header}

    translated = 0
    untranslated = 0

    for pot_entry in pot_entries:
        if pot_entry.is_header or not pot_entry.msgid:
            continue

        po_entry = translations.get(pot_entry.msgid)
        if po_entry and po_entry.msgstr and not po_entry.is_fuzzy:
            translated += 1
        else:
            untranslated += 1

    return (total, translated, untranslated)


def ensure_po_file_exists(pot_file: Path, po_file: Path, language: str) -> bool:
    """Create PO file from POT file if it doesn't exist.

    Args:
        pot_file: Path to POT file
        po_file: Path to PO file
        language: Language code (e.g., 'fr')

    Returns:
        True if PO file exists or was created successfully, False otherwise
    """
    if po_file.exists():
        return True

    if not pot_file.exists():
        _logger.error("POT file not found: %s", pot_file)
        return False

    _logger.info("Creating PO file from POT file: %s", po_file)

    # Ensure i18n directory exists
    po_file.parent.mkdir(parents=True, exist_ok=True)

    # Use msginit to create PO file from POT file
    # --no-translator: Don't prompt for translator info
    # -l: Set language
    # -i: Input POT file
    # -o: Output PO file
    try:
        cmd = [
            "msginit",
            "--no-translator",
            "-l",
            language,
            "-i",
            str(pot_file),
            "-o",
            str(po_file),
        ]
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        _logger.info("Created PO file: %s", po_file)
        return True
    except subprocess.CalledProcessError as e:
        _logger.error("Failed to create PO file: %s", e.stderr)
        return False
    except FileNotFoundError:
        _logger.error("msginit not found. Please install gettext tools.")
        _logger.error("On macOS: brew install gettext")
        _logger.error("On Ubuntu/Debian: apt-get install gettext")
        return False


def translate_with_agent(
    module_path: Path,
    language: str,
    pot_file: Path,
    po_file: Path,
    glossary_path: Path,
    dry_run: bool = False,
    model: str = "gpt-5.2",
) -> bool:
    """Call Codex exec to translate the module.

    Args:
        module_path: Path to module directory
        language: Target language code
        pot_file: Path to POT file
        po_file: Path to PO file
        glossary_path: Path to glossary JSON
        dry_run: If True, don't actually call agent
        model: Model to use (default: gpt-5.2-codex)

    Returns:
        True if successful, False otherwise
    """
    module_name = module_path.name
    lang_name = LANGUAGES.get(language, {}).get("name", language)
    is_rtl = LANGUAGES.get(language, {}).get("rtl", False)

    # Build comprehensive prompt with clear workflow
    rtl_note = "\nNote: This is a right-to-left language. Ensure proper formatting." if is_rtl else ""

    prompt = f"""You are translating an Odoo project module to {lang_name}.

IMPORTANT: You are working in the project root directory: {PROJECT_ROOT}
The module code is located in: odoo/custom/src/project_modules/
All file paths below are ABSOLUTE paths - use them exactly as shown.

Files (use these exact absolute paths):
- POT file: {pot_file} (source English strings)
- PO file: {po_file} (target file - translate empty msgstr entries)
- Glossary: {glossary_path} (use exact terms from 'terms' dict, key '{language}')
- Module directory: {module_path}

WORKFLOW (follow exactly):

OPTION A - Using polib (if available, recommended for easier parsing):
1. Try to use polib if available (optional - helps with filtering/searching):
   ```python
   try:
       import polib
       USE_POLIB = True
   except ImportError:
       USE_POLIB = False
   ```

2. Load the PO file (use polib if available, otherwise read directly):
   ```python
   if USE_POLIB:
       po = polib.pofile(r'{po_file}')
   else:
       with open(r'{po_file}', 'r', encoding='utf-8') as f:
           po_content = f.read()
   ```

3. Load the glossary JSON (use the absolute path):
   ```python
   import json
   with open(r'{glossary_path}', 'r', encoding='utf-8') as f:
       glossary = json.load(f)
   terms = glossary.get('terms', {{}})
   ```

4. Translate empty msgstr entries:
   - If using polib: iterate through `po` entries, check `entry.msgstr`, update `entry.msgstr` for empty ones
   - If not using polib: parse `po_content` to find `msgstr ""` entries and replace them
   - For each empty entry:
     * Extract the `msgid` value
     * Check glossary['terms'] for exact msgid match (case-insensitive)
     * If found in glossary, use terms[key]['{language}'] as translation
     * Otherwise, translate the msgid to {lang_name} MANUALLY (use your language knowledge)
     * Preserve ALL placeholders exactly: %s, %d, %(name)s, {{variable}}, <tags>
     * Use formal language appropriate for government software
   - If `msgstr` already has content: LEAVE IT UNCHANGED

5. Save the updated PO file:
   ```python
   if USE_POLIB:
       po.save(r'{po_file}')
   else:
       with open(r'{po_file}', 'w', encoding='utf-8') as f:
           f.write(po_content)
   ```

PO FILE FORMAT NOTES:
- Each entry has: `msgid "english text"` followed by `msgstr "translation"`
- Empty translations look like: `msgstr ""`
- Preserve all comments, line numbers, and formatting
- Multi-line strings use: `msgid ""` followed by `"line1\n"` `"line2\n"`
- Keep the header intact (first msgid/msgstr pair is usually empty and contains metadata)

IMPORTANT RESTRICTIONS:
- You can use polib if it's already available (helps with filtering/searching entries)
- If polib is not available, edit the PO file directly - read it, parse it, and write it back
- DO NOT install polib or any other libraries - only use what's already available
- DO NOT use any translation libraries (argostranslate, googletrans, deep-translator, etc.)
- DO NOT use any machine translation APIs or services
- Translate strings MANUALLY using your language knowledge
- Use the glossary for domain-specific terms
- For other strings, translate them yourself based on context
- Preserve the exact PO file format and structure

Example translation (for {lang_name}):
   msgid "Contact"
   msgstr "Contacto"  (from glossary: terms['contact']['{language}'] - use key '{language}' for {lang_name})

   msgid "Add %s"
   msgstr "Agregar %s"  (preserve %s placeholder, translate manually to {lang_name})

CRITICAL RULES:
- You can use polib if it's already installed (try `import polib` first) - it helps with filtering/searching
- If polib is not available, edit the PO file directly - read, parse, update empty msgstr entries, write back
- DO NOT install any libraries - only use what's already available (polib, json, etc. are fine if already installed)
- DO NOT use any translation libraries (argostranslate, googletrans, deep-translator, etc.)
- DO NOT use any machine translation APIs, services, or tools
- Translate strings MANUALLY using your language knowledge - you are a bilingual translator
- Use the ABSOLUTE file paths provided above - do NOT use relative paths
- You are working in: {PROJECT_ROOT} (this is the current working directory)
- The module is in: odoo/custom/src/project_modules/{module_name}/
- Preserve placeholders exactly: %s, %d, %(name)s, {{variable}}, <tags>
- Preserve the PO file format exactly - maintain all comments, line breaks, and structure
- Use glossary terms when available (check terms dict)
- Keep existing translations unchanged - only update empty msgstr entries
- Use formal {lang_name} appropriate for government software
{rtl_note}

Execute this workflow now. Do not explore other files or modules - focus only on translating the PO file.
Do not use git commands or check git status - just work with the files directly.
Translate manually - do not use any translation tools or libraries.
Use polib if available for easier parsing, otherwise edit the file directly."""

    if dry_run:
        _logger.info("[DRY-RUN] Would call Codex exec with prompt:")
        _logger.info(prompt[:500] + "...")
        return True

    # Check if codex is available
    codex_cmd = shutil.which("codex")
    if not codex_cmd:
        _logger.error("Codex CLI not found. Please install Codex CLI first.")
        _logger.error("See: https://codex.com/docs/cli")
        return False

    # Call Codex exec
    _logger.info("Calling Codex exec to translate %s to %s...", module_name, language)
    _logger.info("Using model: %s", model)
    _logger.info("=" * 70)
    _logger.info("Streaming agent output (you'll see what it's doing in real-time)...")
    _logger.info("=" * 70)

    # Set working directory to project root so agent can access all files
    try:
        # Use codex exec with:
        # - stdin input for prompt (using - to read from stdin)
        # - --model to specify the model
        # - --full-auto for unattended work (workspace-write sandbox, approvals on failure)
        # - --cd to set working directory
        cmd = [
            codex_cmd,
            "exec",
            "-",  # Read prompt from stdin
            "--profile",
            "translation",  # Use translation profile
            "--model",
            model,
            "--full-auto",  # Enable unattended automation
            "--cd",
            str(PROJECT_ROOT),  # Set working directory
        ]
        result = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            cwd=str(PROJECT_ROOT),  # Set to project root for file access
            # Don't capture output - let it stream to stdout/stderr in real-time
            timeout=600,  # 10 minute timeout
        )

        _logger.info("=" * 70)
        if result.returncode == 0:
            _logger.info("Translation completed successfully")
            return True
        else:
            _logger.error("Codex exec failed with return code %d", result.returncode)
            return False

    except subprocess.TimeoutExpired:
        _logger.error("Codex exec timed out after 10 minutes")
        return False
    except Exception as e:
        _logger.error("Failed to call Codex exec: %s", e)
        return False


def translate_module_iterative(
    module_path: Path,
    language: str,
    glossary_path: Path,
    skip_pot_update: bool = False,
    max_iterations: int = 3,
    dry_run: bool = False,
    database: str = "devel",
    model: str = "gpt-5.2",
) -> tuple[bool, int, int, int]:
    """Translate a module iteratively until complete or max iterations.

    Args:
        module_path: Path to module directory
        language: Target language code
        glossary_path: Path to glossary JSON
        skip_pot_update: If True, skip POT update step
        max_iterations: Maximum number of translation iterations
        dry_run: If True, don't actually translate
        database: Database name for POT update
        model: Model to use for translation

    Returns:
        Tuple of (success, total, translated, untranslated)
    """
    module_name = module_path.name
    _logger.info("=" * 70)
    _logger.info("Processing module: %s (language: %s)", module_name, language)
    _logger.info("=" * 70)

    # Update POT first (this will create it if it doesn't exist)
    if not skip_pot_update:
        _logger.info("Updating POT file for %s...", module_name)
        if not ensure_pot_updated([module_name], database):
            _logger.warning("POT update failed, continuing anyway...")

    # Get file paths (after POT update attempt)
    pot_file = get_pot_file(module_path)
    po_file = get_po_file(module_path, language)

    if not pot_file:
        _logger.warning("No POT file found for %s after update attempt, skipping", module_name)
        return (False, 0, 0, 0)

    # Early check: if skipping POT update and PO file exists and is fully translated, skip everything
    if skip_pot_update and po_file.exists():
        total, translated, untranslated = check_translation_status(pot_file, po_file)
        if untranslated == 0:
            _logger.info("Module %s is already fully translated (skipping POT update)!", module_name)
            return (True, total, translated, untranslated)

    # Ensure PO file exists (create from POT if needed)
    if not ensure_po_file_exists(pot_file, po_file, language):
        _logger.error("Failed to create PO file for %s, skipping", module_name)
        return (False, 0, 0, 0)

    # Check initial status
    total, translated, untranslated = check_translation_status(pot_file, po_file)
    _logger.info("Translation status: %d total, %d translated, %d untranslated", total, translated, untranslated)

    if untranslated == 0:
        _logger.info("Module %s is already fully translated!", module_name)
        return (True, total, translated, untranslated)

    # Iterative translation loop
    for iteration in range(1, max_iterations + 1):
        _logger.info("--- Iteration %d/%d ---", iteration, max_iterations)

        # Call agent
        success = translate_with_agent(
            module_path,
            language,
            pot_file,
            po_file,
            glossary_path,
            dry_run=dry_run,
            model=model,
        )

        if not success:
            _logger.warning("Translation iteration %d failed", iteration)
            break

        # Re-check status
        total, translated, untranslated = check_translation_status(pot_file, po_file)
        _logger.info(
            "After iteration %d: %d total, %d translated, %d untranslated", iteration, total, translated, untranslated
        )

        if untranslated == 0:
            _logger.info("Module %s fully translated after %d iteration(s)!", module_name, iteration)
            return (True, total, translated, untranslated)

    # Max iterations reached
    _logger.warning(
        "Module %s still has %d untranslated strings after %d iterations", module_name, untranslated, max_iterations
    )
    return (False, total, translated, untranslated)


def main():
    parser = argparse.ArgumentParser(
        description="Odoo Translation Agent using Cursor CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--module", "-m", required=True, help="Module name to translate (e.g., trn_vocabulary)")
    parser.add_argument("--lang", "-l", default="fr", help="Target language code (fr, es, ar, lo). Default: fr")
    parser.add_argument("--with-deps", action="store_true", help="Include module dependencies in translation")
    parser.add_argument("--skip-pot-update", action="store_true", help="Skip POT file update (assume already updated)")
    parser.add_argument(
        "--max-iterations", type=int, default=3, help="Maximum number of translation iterations (default: 3)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually translate, just check status and show what would be done"
    )
    parser.add_argument("--database", "-d", default="devel", help="Database name for POT update (default: devel)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--model",
        default="gpt-5.2",
        help="AI model to use for translation (default: gpt-5.2)",
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate language
    if args.lang not in LANGUAGES:
        _logger.warning("Language '%s' not in predefined list, proceeding anyway", args.lang)

    # Find root directory (project_modules)
    # Script is at: odoo/custom/src/project_modules/scripts/translate_agent.py
    # project_modules is at: odoo/custom/src/project_modules
    root_dir = Path(__file__).parent.parent

    # Find glossary
    glossary_path = root_dir / "scripts" / "glossary" / "project-glossary.json"
    if not glossary_path.exists():
        _logger.warning("Glossary not found at %s, continuing without it", glossary_path)

    # Get module path
    module_path = root_dir / args.module
    if not module_path.exists() or not (module_path / "__manifest__.py").exists():
        _logger.error("Module not found: %s", args.module)
        _logger.error("Expected path: %s", module_path)
        sys.exit(1)

    # Handle dependencies
    modules_to_process = [args.module]
    if args.with_deps:
        _logger.info("Expanding module with dependencies...")
        modules_csv = _expand_modules_with_deps(args.module)
        if modules_csv and modules_csv != args.module:
            # Filter to only custom modules (non-Odoo-core)
            deps = [m.strip() for m in modules_csv.split(",") if m.strip() and not m.strip().startswith("base")]
            modules_to_process = sorted(set([args.module] + deps))
            _logger.info("Will process modules: %s", ", ".join(modules_to_process))

    # Process each module
    results = []
    for module_name in modules_to_process:
        module_path = root_dir / module_name
        if not module_path.exists():
            _logger.warning("Module %s not found, skipping", module_name)
            continue

        success, total, translated, untranslated = translate_module_iterative(
            module_path,
            args.lang,
            glossary_path,
            skip_pot_update=args.skip_pot_update,
            max_iterations=args.max_iterations,
            dry_run=args.dry_run,
            database=args.database,
            model=args.model,
        )

        results.append(
            {
                "module": module_name,
                "success": success,
                "total": total,
                "translated": translated,
                "untranslated": untranslated,
            }
        )

    # Summary
    _logger.info("")
    _logger.info("=" * 70)
    _logger.info("TRANSLATION SUMMARY")
    _logger.info("=" * 70)
    for r in results:
        status = "✓" if r["success"] and r["untranslated"] == 0 else "✗"
        _logger.info(
            "%s %s: %d/%d translated (%d untranslated)",
            status,
            r["module"],
            r["translated"],
            r["total"],
            r["untranslated"],
        )

    total_translated = sum(r["translated"] for r in results)
    total_strings = sum(r["total"] for r in results)
    total_untranslated = sum(r["untranslated"] for r in results)

    if total_strings > 0:
        coverage = 100 * total_translated / total_strings
        _logger.info("")
        _logger.info("Overall: %d/%d translated (%.1f%%)", total_translated, total_strings, coverage)

    if total_untranslated > 0 and not args.dry_run:
        _logger.warning("")
        _logger.warning("Some strings remain untranslated. You may need to:")
        _logger.warning("1. Increase --max-iterations")
        _logger.warning("2. Review the PO files manually")
        _logger.warning("3. Check Codex exec output for errors")


if __name__ == "__main__":
    main()
