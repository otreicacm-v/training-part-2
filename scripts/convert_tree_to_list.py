#!/usr/bin/env python3
"""
Convert Odoo 17 tree views to Odoo 19 list views.

In Odoo 19, the view type 'tree' has been renamed to 'list'.
This script converts all <tree> tags to <list> tags in XML view files.
"""

import os
import re
import sys
from pathlib import Path


def convert_tree_to_list(file_path):
    """
    Convert <tree> tags to <list> tags in an XML file.

    Args:
        file_path: Path to the XML file

    Returns:
        tuple: (bool changed, int count) - whether file was changed and number of changes
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # Replace opening <tree> tags with <list>
        # This regex preserves all attributes
        content, count_open = re.subn(r"<tree(\s|>)", r"<list\1", content)

        # Replace closing </tree> tags with </list>
        content, count_close = re.subn(r"</tree>", r"</list>", content)

        total_changes = count_open + count_close

        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True, total_changes

        return False, 0

    except Exception as e:
        print(f"Error processing {file_path}: {e}", file=sys.stderr)
        return False, 0


def find_and_convert_xml_files(base_path):
    """
    Find all XML files and convert tree tags to list tags.

    Args:
        base_path: Base directory to search

    Returns:
        dict: Statistics about the conversion
    """
    stats = {"files_found": 0, "files_changed": 0, "total_changes": 0, "changed_files": []}

    # Find all XML files
    for xml_file in Path(base_path).rglob("*.xml"):
        stats["files_found"] += 1

        changed, count = convert_tree_to_list(xml_file)

        if changed:
            stats["files_changed"] += 1
            stats["total_changes"] += count
            stats["changed_files"].append(str(xml_file))
            print(f"✓ {xml_file.relative_to(base_path)}: {count} changes")

    return stats


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python convert_tree_to_list.py <directory>")
        print("Example: python convert_tree_to_list.py /tmp/odoo19-deps/custom-modules")
        sys.exit(1)

    base_path = sys.argv[1]

    if not os.path.isdir(base_path):
        print(f"Error: {base_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"Converting tree → list in XML files under: {base_path}")
    print("=" * 70)

    stats = find_and_convert_xml_files(base_path)

    print("=" * 70)
    print("\nConversion Summary:")
    print(f"  Files scanned:  {stats['files_found']}")
    print(f"  Files changed:  {stats['files_changed']}")
    print(f"  Total changes:  {stats['total_changes']}")

    if stats["files_changed"] > 0:
        print(f"\n✓ Successfully converted {stats['total_changes']} tree tags to list tags")
        print(f"  in {stats['files_changed']} files")
    else:
        print("\nNo tree tags found to convert.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
