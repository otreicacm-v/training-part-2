#!/usr/bin/env python3
"""
Translation Verification and AI Translation Script

Analyzes translation coverage, verifies glossary compliance, checks English
consistency, and uses AI to translate missing strings with proper context.

Prerequisites:
    # RECOMMENDED: Use API mode (much faster, ~1s per batch)
    pip install anthropic
    export ANTHROPIC_API_KEY=your_key

    # Alternative: CLI mode (slower, ~3min per batch)
    # npm install -g @anthropic-ai/claude-code

Usage:
    # Check English source strings for consistency (no AI needed)
    ./scripts/translate_verify.py --check-english --all

    # Report mode - analyze translation gaps (no AI needed)
    ./scripts/translate_verify.py --report --lang fr --all

    # Verify existing translations against glossary (no AI needed)
    ./scripts/translate_verify.py --verify --lang fr --all

    # Translate missing strings (dry-run)
    ./scripts/translate_verify.py --translate --lang fr --dry-run --all

    # Translate and write to PO files (REQUIRES ANTHROPIC_API_KEY)
    export ANTHROPIC_API_KEY=your_key
    ./scripts/translate_verify.py --translate --lang fr --module trn_vocabulary

    # Translate all modules (use haiku for speed/cost efficiency)
    ./scripts/translate_verify.py --translate --lang fr --all --model claude-haiku

Target Languages:
    - fr: French (primary)
    - es: Spanish
    - ar: Arabic (RTL support)
    - lo: Lao

Glossary:
    The script uses scripts/glossary/project-glossary.json for consistent
    terminology. Update this file when adding new domain-specific terms.
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Try to import anthropic for direct API access (faster)
try:
    import anthropic

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
_logger = logging.getLogger(__name__)

# Language metadata
LANGUAGES = {
    "fr": {"name": "French", "plural_forms": "nplurals=2; plural=n > 1;"},
    "es": {"name": "Spanish", "plural_forms": "nplurals=2; plural=n != 1;"},
    "ar": {
        "name": "Arabic",
        "plural_forms": (
            "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 :" " n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5;"
        ),
        "rtl": True,
    },
    "lo": {"name": "Lao", "plural_forms": "nplurals=1; plural=0;"},
}

# AI model configuration
AI_MODELS = {
    "claude": "claude-sonnet-4-5-20250929",
    "claude-haiku": "claude-haiku",
    "claude-opus": "claude-opus",
}


@dataclass
class POEntry:
    """Represents a single PO file entry."""

    msgid: str
    msgstr: str = ""
    comments: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    occurrences: list = field(default_factory=list)
    is_fuzzy: bool = False
    is_header: bool = False
    context_type: str = ""  # field, model, view, code, menu


@dataclass
class TranslationReport:
    """Translation analysis report for a module."""

    module: str
    language: str
    total_strings: int = 0
    translated: int = 0
    untranslated: int = 0
    fuzzy: int = 0
    glossary_violations: list = field(default_factory=list)
    placeholder_errors: list = field(default_factory=list)


def parse_po_file(filepath: Path) -> list[POEntry]:  # noqa: C901
    """Parse a PO file and return list of entries."""
    entries = []
    current_entry = None
    current_field = None

    if not filepath.exists():
        return entries

    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        line = line.rstrip("\n")

        # Comments
        if line.startswith("#. "):
            if current_entry is None:
                current_entry = POEntry(msgid="")
            current_entry.comments.append(line[3:])
            # Extract context type
            if "model:" in line:
                current_entry.context_type = "model"
            elif "field" in line.lower():
                current_entry.context_type = "field"
            elif "view" in line.lower():
                current_entry.context_type = "view"
            elif "code:" in line.lower():
                current_entry.context_type = "code"
        elif line.startswith("#: "):
            if current_entry is None:
                current_entry = POEntry(msgid="")
            current_entry.occurrences.append(line[3:])
        elif line.startswith("#, "):
            if current_entry is None:
                current_entry = POEntry(msgid="")
            flags = line[3:].split(",")
            current_entry.flags.extend([f.strip() for f in flags])
            if "fuzzy" in current_entry.flags:
                current_entry.is_fuzzy = True
        elif line.startswith("#"):
            # Other comments, skip
            pass
        elif line.startswith('msgid "'):
            if current_entry is None:
                current_entry = POEntry(msgid="")
            current_entry.msgid = line[7:-1]  # Remove msgid " and trailing "
            current_field = "msgid"
        elif line.startswith('msgstr "'):
            if current_entry:
                current_entry.msgstr = line[8:-1]
                current_field = "msgstr"
        elif line.startswith('"') and line.endswith('"'):
            # Continuation line
            if current_entry and current_field:
                value = line[1:-1]
                if current_field == "msgid":
                    current_entry.msgid += value
                elif current_field == "msgstr":
                    current_entry.msgstr += value
        elif line == "":
            # Empty line = end of entry
            if current_entry and current_entry.msgid:
                entries.append(current_entry)
            elif current_entry and not current_entry.msgid:
                current_entry.is_header = True
                entries.append(current_entry)
            current_entry = None
            current_field = None

    # Don't forget last entry
    if current_entry:
        if current_entry.msgid:
            entries.append(current_entry)
        elif current_entry.msgstr:
            current_entry.is_header = True
            entries.append(current_entry)

    return entries


def write_po_file(filepath: Path, entries: list[POEntry], language: str, module: str):
    """Write entries back to a PO file."""
    lang_meta = LANGUAGES.get(language, {})

    with open(filepath, "w", encoding="utf-8") as f:
        # Write header
        f.write(f"""# Translation of Odoo Server.
# This file contains the translation of the following modules:
# \t* {module}
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Server 19.0\\n"
"Report-Msgid-Bugs-To: \\n"
"Language: {language}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: {lang_meta.get('plural_forms', 'nplurals=2; plural=n != 1;')}\\n"
"X-Generator: Odoo AI Translation\\n"

""")

        for entry in entries:
            if entry.is_header:
                continue

            # Write comments
            for comment in entry.comments:
                f.write(f"#. {comment}\n")

            # Write occurrences
            for occ in entry.occurrences:
                f.write(f"#: {occ}\n")

            # Write flags
            if entry.flags:
                f.write(f"#, {', '.join(entry.flags)}\n")

            # Write msgid (handle multiline)
            if "\n" in entry.msgid or len(entry.msgid) > 70:
                f.write('msgid ""\n')
                for part in _split_string(entry.msgid):
                    f.write(f'"{part}"\n')
            else:
                f.write(f'msgid "{_escape_po(entry.msgid)}"\n')

            # Write msgstr
            if "\n" in entry.msgstr or len(entry.msgstr) > 70:
                f.write('msgstr ""\n')
                for part in _split_string(entry.msgstr):
                    f.write(f'"{part}"\n')
            else:
                f.write(f'msgstr "{_escape_po(entry.msgstr)}"\n')

            f.write("\n")


def _escape_po(s: str) -> str:
    """Escape special characters for PO format."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _split_string(s: str, max_len: int = 70) -> list[str]:
    """Split a string for PO file multiline format."""
    parts = []
    s = _escape_po(s)
    while len(s) > max_len:
        # Find a good break point
        break_at = s.rfind(" ", 0, max_len)
        if break_at == -1:
            break_at = max_len
        parts.append(s[:break_at])
        s = s[break_at:].lstrip()
    if s:
        parts.append(s)
    return parts


def load_glossary(glossary_path: Path) -> dict:
    """Load the glossary JSON file."""
    if not glossary_path.exists():
        _logger.warning(f"Glossary not found at {glossary_path}")
        return {"terms": {}, "ui_labels": {}}

    with open(glossary_path, encoding="utf-8") as f:
        return json.load(f)


def check_glossary_compliance(msgid: str, msgstr: str, language: str, glossary: dict) -> list[str]:
    """Check if translation uses correct glossary terms."""
    violations = []

    all_terms = {**glossary.get("terms", {}), **glossary.get("ui_labels", {})}

    for _term_key, translations in all_terms.items():
        en_term = translations.get("en", "").lower()
        expected = translations.get(language, "")

        if not en_term or not expected:
            continue

        # Check if English term appears in msgid
        if en_term in msgid.lower():
            # Check if correct translation appears in msgstr
            if expected.lower() not in msgstr.lower() and msgstr:
                violations.append(f"Term '{en_term}' should be translated as '{expected}', " f"but found: '{msgstr}'")

    return violations


def extract_placeholders(s: str) -> set[str]:
    """Extract placeholders from a string."""
    placeholders = set()

    # Python format: %s, %d, %(name)s
    placeholders.update(re.findall(r"%(?:\([^)]+\))?[sdifFeEgGxXo]", s))

    # Curly brace format: {}, {name}, {0}
    placeholders.update(re.findall(r"\{[^}]*\}", s))

    # HTML tags (should be preserved)
    placeholders.update(re.findall(r"<[^>]+>", s))

    return placeholders


def check_placeholders(msgid: str, msgstr: str) -> list[str]:
    """Check if placeholders are preserved in translation."""
    errors = []

    if not msgstr:
        return errors

    src_placeholders = extract_placeholders(msgid)
    dst_placeholders = extract_placeholders(msgstr)

    missing = src_placeholders - dst_placeholders
    extra = dst_placeholders - src_placeholders

    if missing:
        errors.append(f"Missing placeholders: {missing}")
    if extra:
        errors.append(f"Extra placeholders: {extra}")

    return errors


def find_modules(root_dir: Path, pattern: str = "trn_*") -> list[Path]:
    """Find all custom modules."""
    modules = []
    for path in root_dir.glob(pattern):
        if path.is_dir() and (path / "__manifest__.py").exists():
            modules.append(path)
    return sorted(modules)


def get_pot_file(module_path: Path) -> Path | None:
    """Get the POT template file for a module."""
    i18n_dir = module_path / "i18n"
    if not i18n_dir.exists():
        return None

    module_name = module_path.name
    pot_file = i18n_dir / f"{module_name}.pot"

    if pot_file.exists():
        return pot_file

    # Try to find any .pot file
    pot_files = list(i18n_dir.glob("*.pot"))
    return pot_files[0] if pot_files else None


def get_po_file(module_path: Path, language: str) -> Path:
    """Get or create path for PO file."""
    i18n_dir = module_path / "i18n"
    i18n_dir.mkdir(exist_ok=True)
    return i18n_dir / f"{language}.po"


def analyze_module(module_path: Path, language: str, glossary: dict) -> TranslationReport:
    """Analyze translation status for a module."""
    module_name = module_path.name
    report = TranslationReport(module=module_name, language=language)

    pot_file = get_pot_file(module_path)
    po_file = get_po_file(module_path, language)

    # Parse POT for source strings
    pot_entries = parse_po_file(pot_file) if pot_file else []
    po_entries = parse_po_file(po_file) if po_file.exists() else []

    # Create lookup for existing translations
    translations = {e.msgid: e for e in po_entries if not e.is_header}

    for pot_entry in pot_entries:
        if pot_entry.is_header or not pot_entry.msgid:
            continue

        report.total_strings += 1

        po_entry = translations.get(pot_entry.msgid)

        if po_entry and po_entry.msgstr:
            if po_entry.is_fuzzy:
                report.fuzzy += 1
            else:
                report.translated += 1

            # Check glossary compliance
            violations = check_glossary_compliance(pot_entry.msgid, po_entry.msgstr, language, glossary)
            report.glossary_violations.extend(violations)

            # Check placeholders
            placeholder_errors = check_placeholders(pot_entry.msgid, po_entry.msgstr)
            report.placeholder_errors.extend(placeholder_errors)
        else:
            report.untranslated += 1

    return report


def build_translation_prompt(
    msgid: str,
    context_type: str,
    comments: list[str],
    language: str,
    glossary: dict,
    examples: list[tuple[str, str]] = None,
) -> str:
    """Build a prompt for AI translation."""
    lang_name = LANGUAGES.get(language, {}).get("name", language)
    is_rtl = LANGUAGES.get(language, {}).get("rtl", False)

    # Build glossary section
    glossary_terms = []
    all_terms = {**glossary.get("terms", {}), **glossary.get("ui_labels", {})}
    for _term_key, translations in all_terms.items():
        en = translations.get("en", "")
        target = translations.get(language, "")
        if en and target:
            glossary_terms.append(f"  - {en} → {target}")

    glossary_section = "\n".join(glossary_terms[:30])  # Limit to avoid token overflow

    # Extract placeholders
    placeholders = extract_placeholders(msgid)
    placeholder_note = ""
    if placeholders:
        placeholder_note = f"\nPLACEHOLDERS TO PRESERVE: {', '.join(placeholders)}"

    # Context
    context_info = f"Context: {context_type or 'general'}"
    if comments:
        context_info += f"\nOdoo reference: {'; '.join(comments[:3])}"

    # Examples
    examples_section = ""
    if examples:
        examples_section = "\nEXAMPLES from same module:\n"
        for src, dst in examples[:5]:
            examples_section += f'  "{src}" → "{dst}"\n'

    # RTL note
    rtl_note = ""
    if is_rtl:
        rtl_note = "\nNote: This is a right-to-left language. Ensure proper formatting."

    prompt = f"""Translate the following string to {lang_name} for a health information system.

GLOSSARY (use these exact terms):
{glossary_section}

{context_info}
{placeholder_note}
{examples_section}
{rtl_note}

SOURCE: "{msgid}"

Return ONLY the translation, nothing else. No quotes, no explanation."""

    return prompt


def translate_with_ai(prompt: str, model: str = "claude", dry_run: bool = False, use_cli: bool = False) -> str | None:
    """Call AI to translate a string.

    Uses Anthropic API directly if available (faster), falls back to CLI.
    """
    if dry_run:
        _logger.info(f"[DRY-RUN] Would translate with prompt:\n{prompt[:200]}...")
        return None

    # Model mapping for API
    api_model_map = {
        "claude": "claude-sonnet-4-5-20250929",
        "claude-haiku": "claude-3-5-haiku-latest",
        "claude-opus": "claude-opus-4-5-20251101",
    }

    # Try API first (much faster)
    if HAS_ANTHROPIC and not use_cli and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            client = anthropic.Anthropic()
            model_id = api_model_map.get(model, "claude-sonnet-4-5-20250929")

            message = client.messages.create(
                model=model_id, max_tokens=256, messages=[{"role": "user", "content": prompt}]
            )

            response = message.content[0].text.strip()
            # Clean up response
            response = response.strip("`\"'")
            if response.startswith("```"):
                response = response.split("\n", 1)[-1].rsplit("```", 1)[0]
            return response.strip()

        except anthropic.RateLimitError:
            _logger.warning("Rate limited, waiting 5s...")
            time.sleep(5)
            return translate_with_ai(prompt, model, dry_run, use_cli)
        except anthropic.APIError as e:
            _logger.error(f"API error: {e}")
            return None

    # Fall back to CLI
    try:
        cli_model_map = {
            "claude": "sonnet",
            "claude-haiku": "haiku",
            "claude-opus": "opus",
        }
        model_arg = cli_model_map.get(model, "sonnet")

        result = subprocess.run(
            ["claude", "-p", "--model", model_arg, prompt], capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            response = result.stdout.strip()
            response = response.strip("`\"'")
            if response.startswith("```"):
                response = response.split("\n", 1)[-1].rsplit("```", 1)[0]
            return response.strip()
        else:
            _logger.error(f"CLI translation failed: {result.stderr}")
            return None
    except FileNotFoundError:
        _logger.error("Claude CLI not found. Install anthropic package or claude CLI")
        return None
    except subprocess.TimeoutExpired:
        _logger.error("CLI translation timed out")
        return None


def batch_translate(
    strings: list[tuple[str, str, list[str]]],  # (msgid, context_type, comments)
    language: str,
    glossary: dict,
    model: str = "claude",
    use_cli: bool = False,
    batch_size: int = 20,
) -> dict[str, str]:
    """Translate multiple strings in one API call for efficiency.

    Returns a dict mapping msgid -> translation.
    """
    lang_name = LANGUAGES.get(language, {}).get("name", language)
    results = {}

    # Build glossary section - prioritize terms that appear in the strings
    all_terms = {**glossary.get("terms", {}), **glossary.get("status_labels", {}), **glossary.get("ui_labels", {})}

    # Collect all msgids to find relevant terms
    all_msgids = " ".join([s[0].lower() for s in strings])

    # Separate into relevant (appear in strings) and other terms
    relevant_terms = []
    other_terms = []
    for _term_key, translations in all_terms.items():
        en = translations.get("en", "")
        target = translations.get(language, "")
        if en and target:
            term_line = f"  {en} = {target}"
            # Check if term appears in any of the strings
            if en.lower() in all_msgids:
                relevant_terms.append(term_line)
            else:
                other_terms.append(term_line)

    # Prioritize relevant terms, then fill with others (max 60 terms)
    glossary_terms = relevant_terms[:40] + other_terms[: max(0, 60 - len(relevant_terms))]
    glossary_section = "\n".join(glossary_terms)

    # Process in batches
    for i in range(0, len(strings), batch_size):
        batch = strings[i : i + batch_size]

        # Build batch prompt
        strings_section = ""
        for idx, (msgid, ctx_type, _comments) in enumerate(batch, 1):
            ctx_info = f"[{ctx_type}]" if ctx_type else ""
            strings_section += f'{idx}. {ctx_info} "{msgid}"\n'

        prompt = f"""Translate these {len(batch)} strings to {lang_name} for a health information system.

GLOSSARY (use these exact terms when they appear):
{glossary_section}

STRINGS TO TRANSLATE:
{strings_section}

RULES:
- Return ONLY the translations, one per line, numbered to match
- Preserve all placeholders: %s, %d, {{name}}, %(var)s, <tags>
- Use formal language appropriate for government software
- Keep it concise

Return format (exactly {len(batch)} lines):
1. [translation]
2. [translation]
..."""

        # Call AI
        response = None
        if HAS_ANTHROPIC and not use_cli and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                client = anthropic.Anthropic()
                api_model_map = {
                    "claude": "claude-sonnet-4-5-20250929",
                    "claude-haiku": "claude-3-5-haiku-latest",
                    "claude-opus": "claude-opus-4-5-20251101",
                }
                model_id = api_model_map.get(model, "claude-sonnet-4-5-20250929")
                message = client.messages.create(
                    model=model_id, max_tokens=2048, messages=[{"role": "user", "content": prompt}]
                )
                response = message.content[0].text.strip()
            except Exception as e:
                _logger.error(f"API batch translation failed: {e}")
        else:
            # CLI mode
            try:
                cli_model_map = {
                    "claude": "sonnet",
                    "claude-haiku": "haiku",
                    "claude-opus": "opus",
                }
                model_arg = cli_model_map.get(model, "sonnet")
                result = subprocess.run(
                    ["claude", "-p", "--model", model_arg, prompt], capture_output=True, text=True, timeout=180
                )
                if result.returncode == 0:
                    response = result.stdout.strip()
            except Exception as e:
                _logger.error(f"CLI batch translation failed: {e}")

        # Parse response
        if response:
            lines = response.strip().split("\n")
            for line in lines:
                # Try to parse "1. translation" or just "translation"
                match = re.match(r"^\d+\.\s*(.+)$", line.strip())
                if match:
                    translation = match.group(1).strip().strip("\"'")
                    # Find which msgid this corresponds to
                    line_num = int(re.match(r"^(\d+)", line).group(1))
                    if 1 <= line_num <= len(batch):
                        msgid = batch[line_num - 1][0]
                        results[msgid] = translation

        _logger.info(
            f"  Batch {i//batch_size + 1}: translated {len([r for r in results if r in [b[0] for b in batch]])} strings"
        )

    return results


def translate_module(
    module_path: Path,
    language: str,
    glossary: dict,
    dry_run: bool = False,
    model: str = "claude",
    use_cli: bool = False,
) -> TranslationReport:
    """Translate missing strings in a module."""
    module_name = module_path.name
    _logger.info(f"[{module_name}] Starting translation to {language}...")

    pot_file = get_pot_file(module_path)
    po_file = get_po_file(module_path, language)

    if not pot_file:
        _logger.warning(f"[{module_name}] No POT file found, skipping")
        return TranslationReport(module=module_name, language=language)

    # Parse files
    pot_entries = parse_po_file(pot_file)
    po_entries = parse_po_file(po_file) if po_file.exists() else []

    # Create lookup
    translations = {e.msgid: e for e in po_entries if not e.is_header}

    # Track stats
    report = TranslationReport(module=module_name, language=language)
    new_entries = []
    translated_count = 0

    # Collect strings that need translation
    to_translate = []  # (pot_entry, msgid, context_type, comments)
    entries_map = {}  # msgid -> pot_entry for later lookup

    for pot_entry in pot_entries:
        if pot_entry.is_header or not pot_entry.msgid:
            continue

        report.total_strings += 1
        existing = translations.get(pot_entry.msgid)

        if existing and existing.msgstr and not existing.is_fuzzy:
            # Already translated
            report.translated += 1
            new_entries.append(existing)
        elif existing and existing.is_fuzzy:
            # Fuzzy - could re-translate, for now keep
            report.fuzzy += 1
            new_entries.append(existing)
        else:
            # Needs translation - collect for batch
            report.untranslated += 1
            to_translate.append((pot_entry.msgid, pot_entry.context_type, pot_entry.comments))
            entries_map[pot_entry.msgid] = pot_entry

    # Batch translate if we have strings
    batch_results = {}
    if to_translate and not dry_run:
        _logger.info(f"[{module_name}] Translating {len(to_translate)} strings in batches...")
        batch_results = batch_translate(
            to_translate,
            language,
            glossary,
            model=model,
            use_cli=use_cli,
            batch_size=15,  # Smaller batches for better accuracy
        )
    elif dry_run:
        _logger.info(f"[{module_name}] [DRY-RUN] Would translate {len(to_translate)} strings")

    # Build entries from batch results
    for msgid, _context_type, _comments in to_translate:
        pot_entry = entries_map[msgid]
        translation = batch_results.get(msgid, "")

        if translation:
            new_entry = POEntry(
                msgid=pot_entry.msgid,
                msgstr=translation,
                comments=pot_entry.comments,
                occurrences=pot_entry.occurrences,
                flags=pot_entry.flags,
                context_type=pot_entry.context_type,
            )
            new_entries.append(new_entry)
            translated_count += 1
        else:
            # Keep empty entry
            new_entry = POEntry(
                msgid=pot_entry.msgid,
                msgstr="",
                comments=pot_entry.comments,
                occurrences=pot_entry.occurrences,
                context_type=pot_entry.context_type,
            )
            new_entries.append(new_entry)

    # Write back if not dry-run
    if not dry_run and translated_count > 0:
        write_po_file(po_file, new_entries, language, module_name)
        _logger.info(f"[{module_name}] Wrote {translated_count} new translations to {po_file}")

    return report


def generate_report(reports: list[TranslationReport], output_path: Path):
    """Generate summary report."""
    summary = {
        "total_modules": len(reports),
        "total_strings": sum(r.total_strings for r in reports),
        "total_translated": sum(r.translated for r in reports),
        "total_untranslated": sum(r.untranslated for r in reports),
        "total_fuzzy": sum(r.fuzzy for r in reports),
        "coverage_percent": 0,
        "modules": [],
    }

    if summary["total_strings"] > 0:
        summary["coverage_percent"] = round(100 * summary["total_translated"] / summary["total_strings"], 1)

    for r in reports:
        coverage = 0
        if r.total_strings > 0:
            coverage = round(100 * r.translated / r.total_strings, 1)

        summary["modules"].append(
            {
                "module": r.module,
                "language": r.language,
                "total": r.total_strings,
                "translated": r.translated,
                "untranslated": r.untranslated,
                "fuzzy": r.fuzzy,
                "coverage_percent": coverage,
                "glossary_violations": len(r.glossary_violations),
                "placeholder_errors": len(r.placeholder_errors),
            }
        )

    # Sort by coverage (lowest first for priority)
    summary["modules"].sort(key=lambda x: x["coverage_percent"])

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


def check_english_consistency(modules: list[Path], glossary: dict, output_path: Path) -> dict:  # noqa: C901
    """
    Check English source strings for consistency across all modules.

    Detects:
    - Case variations of the same term
    - Terms not matching glossary preferred forms
    - Similar terms that might need standardization
    - Potential typos or inconsistencies
    """
    from collections import defaultdict
    from difflib import SequenceMatcher

    # Collect all English strings with their locations
    all_strings = []  # [(msgid, module, context_type)]
    string_locations = defaultdict(list)  # msgid.lower() -> [(msgid, module, context)]

    for module_path in modules:
        module_name = module_path.name
        pot_file = get_pot_file(module_path)
        if not pot_file:
            continue

        entries = parse_po_file(pot_file)
        for entry in entries:
            if entry.is_header or not entry.msgid:
                continue
            all_strings.append((entry.msgid, module_name, entry.context_type))
            string_locations[entry.msgid.lower()].append((entry.msgid, module_name, entry.context_type))

    _logger.info(f"Collected {len(all_strings)} English strings from {len(modules)} modules")

    # Build glossary lookup
    glossary_terms = {}
    for _term_key, translations in glossary.get("terms", {}).items():
        en = translations.get("en", "")
        if en:
            glossary_terms[en.lower()] = en

    for _term_key, translations in glossary.get("status_labels", {}).items():
        en = translations.get("en", "")
        if en:
            glossary_terms[en.lower()] = en

    for _term_key, translations in glossary.get("ui_labels", {}).items():
        en = translations.get("en", "")
        if en:
            glossary_terms[en.lower()] = en

    # Find inconsistencies
    issues = {
        "case_variations": [],  # Same term with different capitalization
        "glossary_mismatches": [],  # Terms not using glossary preferred form
        "similar_terms": [],  # Terms that look similar (potential duplicates)
        "summary": {},
    }

    # 1. Find case variations
    seen_normalized = defaultdict(set)  # normalized -> set of actual forms
    for msgid, _module, _ctx in all_strings:
        # Skip very short strings or strings with placeholders
        if len(msgid) < 3 or "%" in msgid:
            continue
        normalized = msgid.lower().strip()
        seen_normalized[normalized].add(msgid)

    for normalized, variations in seen_normalized.items():
        if len(variations) > 1:
            # Found inconsistency - different capitalizations
            var_list = sorted(variations)
            locations = string_locations[normalized]
            modules_affected = sorted(set(loc[1] for loc in locations))
            issues["case_variations"].append(
                {
                    "term": normalized,
                    "variations": var_list,
                    "count": len(locations),
                    "modules": modules_affected[:5],  # Limit for readability
                    "suggested": glossary_terms.get(normalized, var_list[0]),
                }
            )

    # 2. Check against glossary for preferred forms
    for msgid, mod, ctx in all_strings:
        msgid_lower = msgid.lower().strip()
        # Check each glossary term
        for term_lower, preferred in glossary_terms.items():
            # Exact match but wrong case
            if msgid_lower == term_lower and msgid != preferred:
                issues["glossary_mismatches"].append(
                    {"found": msgid, "expected": preferred, "module": mod, "context": ctx}
                )
            # Also check if term appears within the string
            elif term_lower in msgid_lower and len(term_lower) > 4:
                # Find the actual casing used in the string
                start_idx = msgid_lower.find(term_lower)
                actual_term = msgid[start_idx : start_idx + len(term_lower)]
                if actual_term != preferred and actual_term.lower() == term_lower:
                    issues["glossary_mismatches"].append(
                        {
                            "found": f"'{actual_term}' in '{msgid}'",
                            "expected": preferred,
                            "module": mod,
                            "context": ctx,
                        }
                    )

    # Deduplicate glossary mismatches
    seen_mismatches = set()
    unique_mismatches = []
    for m in issues["glossary_mismatches"]:
        key = (m["found"], m["expected"])
        if key not in seen_mismatches:
            seen_mismatches.add(key)
            unique_mismatches.append(m)
    issues["glossary_mismatches"] = unique_mismatches[:100]  # Limit output

    # 3. Find similar terms (potential duplicates/typos)
    unique_terms = list(set(s[0] for s in all_strings if len(s[0]) > 5))
    similar_pairs = []

    # Compare terms for similarity (only short terms to avoid noise)
    short_terms = [t for t in unique_terms if 5 < len(t) < 40 and "%" not in t]

    for i, term1 in enumerate(short_terms[:200]):  # Limit for performance
        for term2 in short_terms[i + 1 : 200]:
            if term1.lower() == term2.lower():
                continue  # Already caught by case variations
            ratio = SequenceMatcher(None, term1.lower(), term2.lower()).ratio()
            if 0.85 < ratio < 1.0:  # Very similar but not identical
                similar_pairs.append({"term1": term1, "term2": term2, "similarity": round(ratio * 100, 1)})

    issues["similar_terms"] = sorted(similar_pairs, key=lambda x: x["similarity"], reverse=True)[:50]

    # Generate summary
    issues["summary"] = {
        "total_strings": len(all_strings),
        "unique_strings": len(set(s[0] for s in all_strings)),
        "modules_scanned": len(modules),
        "case_variation_groups": len(issues["case_variations"]),
        "glossary_mismatches": len(issues["glossary_mismatches"]),
        "similar_term_pairs": len(issues["similar_terms"]),
    }

    # Write report
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(issues, f, indent=2, ensure_ascii=False)

    return issues


def print_english_consistency_report(issues: dict):
    """Print English consistency report to console."""
    print("\n" + "=" * 70)
    print("ENGLISH CONSISTENCY REPORT")
    print("=" * 70)

    summary = issues["summary"]
    print(f"Total strings scanned:    {summary['total_strings']}")
    print(f"Unique strings:           {summary['unique_strings']}")
    print(f"Modules scanned:          {summary['modules_scanned']}")
    print()

    # Case variations
    print("CASE VARIATIONS (same term, different capitalization):")
    print("-" * 70)
    if issues["case_variations"]:
        for item in issues["case_variations"][:15]:
            print(f"  '{item['term']}'")
            print(f"    Variations: {', '.join(item['variations'])}")
            print(f"    Suggested:  {item['suggested']}")
            print(f"    Modules:    {', '.join(item['modules'][:3])}")
            print()
        if len(issues["case_variations"]) > 15:
            print(f"  ... and {len(issues['case_variations']) - 15} more")
    else:
        print("  No case variations found!")
    print()

    # Glossary mismatches
    print("GLOSSARY MISMATCHES (terms not using preferred form):")
    print("-" * 70)
    if issues["glossary_mismatches"]:
        for item in issues["glossary_mismatches"][:15]:
            print(f"  Found:    {item['found']}")
            print(f"  Expected: {item['expected']}")
            print(f"  Module:   {item['module']}")
            print()
        if len(issues["glossary_mismatches"]) > 15:
            print(f"  ... and {len(issues['glossary_mismatches']) - 15} more")
    else:
        print("  No glossary mismatches found!")
    print()

    # Similar terms
    print("SIMILAR TERMS (potential duplicates or typos):")
    print("-" * 70)
    if issues["similar_terms"]:
        for item in issues["similar_terms"][:10]:
            print(f"  '{item['term1']}' <-> '{item['term2']}' ({item['similarity']}% similar)")
        if len(issues["similar_terms"]) > 10:
            print(f"  ... and {len(issues['similar_terms']) - 10} more")
    else:
        print("  No similar terms found!")
    print()


def print_report_summary(summary: dict):
    """Print report summary to console."""
    print("\n" + "=" * 60)
    print("TRANSLATION COVERAGE REPORT")
    print("=" * 60)
    print(f"Total modules:      {summary['total_modules']}")
    print(f"Total strings:      {summary['total_strings']}")
    print(f"Translated:         {summary['total_translated']}")
    print(f"Untranslated:       {summary['total_untranslated']}")
    print(f"Fuzzy:              {summary['total_fuzzy']}")
    print(f"Coverage:           {summary['coverage_percent']}%")
    print()

    print("MODULES BY COVERAGE (lowest first):")
    print("-" * 60)
    for m in summary["modules"][:20]:
        bar = "█" * int(m["coverage_percent"] / 5) + "░" * (20 - int(m["coverage_percent"] / 5))
        print(f"  {m['module'][:30]:<30} {bar} {m['coverage_percent']:>5.1f}%")

    if len(summary["modules"]) > 20:
        print(f"  ... and {len(summary['modules']) - 20} more modules")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Translation Verification and AI Translation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument("--lang", "-l", default="fr", help="Target language code (fr, es, ar, lo)")
    parser.add_argument("--module", "-m", help="Specific module to process (e.g., trn_vocabulary)")
    parser.add_argument("--all", "-a", action="store_true", help="Process all trn_* modules")
    parser.add_argument("--report", action="store_true", help="Generate coverage report only")
    parser.add_argument("--verify", action="store_true", help="Verify existing translations against glossary")
    parser.add_argument(
        "--check-english", action="store_true", help="Check English source strings for consistency across modules"
    )
    parser.add_argument("--translate", action="store_true", help="Translate missing strings using AI")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes, just show what would be done")
    parser.add_argument(
        "--model", default="claude", choices=list(AI_MODELS.keys()), help="AI model to use for translation"
    )
    parser.add_argument("--glossary", help="Path to glossary JSON file")
    parser.add_argument(
        "--use-cli", action="store_true", help="Force using Claude CLI instead of API (slower but no API key needed)"
    )

    args = parser.parse_args()

    # Validate language
    if args.lang not in LANGUAGES:
        _logger.warning(f"Language '{args.lang}' not in predefined list, proceeding anyway")

    # Find root directory
    root_dir = Path(__file__).parent.parent

    # Load glossary
    glossary_path = (
        Path(args.glossary) if args.glossary else (root_dir / "scripts" / "glossary" / "project-glossary.json")
    )
    glossary = load_glossary(glossary_path)
    _logger.info(f"Loaded glossary with {len(glossary.get('terms', {}))} terms")

    # Find modules to process
    if args.module:
        module_path = root_dir / args.module
        if not module_path.exists():
            _logger.error(f"Module not found: {args.module}")
            sys.exit(1)
        modules = [module_path]
    elif args.all:
        modules = find_modules(root_dir)
    else:
        # Default: show usage
        parser.print_help()
        print("\nExamples:")
        print("  ./scripts/translate_verify.py --report --lang fr --all")
        print("  ./scripts/translate_verify.py --translate --lang fr --module trn_vocabulary")
        sys.exit(0)

    _logger.info(f"Processing {len(modules)} modules for language: {args.lang}")

    # Set up report directory
    report_dir = root_dir / "reports" / "translations"
    report_dir.mkdir(parents=True, exist_ok=True)

    reports = []

    if args.report or args.verify:
        # Analysis mode
        for module_path in modules:
            report = analyze_module(module_path, args.lang, glossary)
            reports.append(report)

            if args.verify and (report.glossary_violations or report.placeholder_errors):
                _logger.warning(f"[{report.module}] Found issues:")
                for v in report.glossary_violations[:5]:
                    _logger.warning(f"  Glossary: {v}")
                for e in report.placeholder_errors[:5]:
                    _logger.warning(f"  Placeholder: {e}")

        # Generate summary
        summary = generate_report(reports, report_dir / f"summary_{args.lang}.json")
        print_report_summary(summary)

    elif args.check_english:
        # English consistency check mode
        _logger.info("Checking English source strings for consistency...")
        output_path = report_dir / "english_consistency.json"
        issues = check_english_consistency(modules, glossary, output_path)
        print_english_consistency_report(issues)
        print(f"\nFull report saved to: {output_path}")

    elif args.translate:
        # Translation mode
        use_cli = getattr(args, "use_cli", False)
        if not HAS_ANTHROPIC and not use_cli:
            _logger.info("anthropic package not installed, using CLI mode")
            _logger.info("Install with: pip install anthropic")
        elif not os.environ.get("ANTHROPIC_API_KEY") and not use_cli:
            _logger.info("ANTHROPIC_API_KEY not set, using CLI mode")

        for module_path in modules:
            report = translate_module(
                module_path, args.lang, glossary, dry_run=args.dry_run, model=args.model, use_cli=use_cli
            )
            reports.append(report)

        # Generate summary
        summary = generate_report(reports, report_dir / f"translation_{args.lang}.json")
        print_report_summary(summary)

        if not args.dry_run:
            print("\nTranslations written to module i18n/ directories")
            print(f"Report saved to: {report_dir / f'translation_{args.lang}.json'}")


if __name__ == "__main__":
    main()
