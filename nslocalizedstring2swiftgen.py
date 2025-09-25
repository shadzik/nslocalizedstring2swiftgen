#!/usr/bin/env python3

import os
import re
import argparse
from pathlib import Path

def snake_to_camel_case(snake_str):
    """Convert snake_case to camelCase, or preserve camelCase if already in that format"""
    # If the string doesn't contain underscores, it's likely already camelCase
    if '_' not in snake_str:
        # Ensure first letter is lowercase (in case it's PascalCase)
        return snake_str[0].lower() + snake_str[1:] if snake_str else snake_str
    
    # Convert snake_case to camelCase
    components = snake_str.split('_')
    return components[0].lower() + ''.join(word.capitalize() for word in components[1:])

def parse_localizable_strings(localizable_path):
    """Parse Localizable.strings file and return a dict of key mappings"""
    key_mappings = {}
    
    if not os.path.exists(localizable_path):
        print(f"Warning: {localizable_path} not found")
        return key_mappings
    
    with open(localizable_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Match string entries: "key" = "value";
    pattern = r'"([^"]+)"\s*=\s*"[^"]*"\s*;'
    matches = re.findall(pattern, content)
    
    for key in matches:
        camel_case_key = snake_to_camel_case(key)
        key_mappings[key] = f"L10n.{camel_case_key}"
    
    print(f"Found {len(key_mappings)} localizable keys")
    return key_mappings

def replace_nslocalizedstring_in_file(file_path, key_mappings, dry_run=False):
    """Replace NSLocalizedString calls in a single Swift file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        print(f"Warning: Could not read {file_path} (encoding issue)")
        return 0, 0
    
    original_content = content
    replacements_made = 0
    unmatched_keys = set()
    
    # Pattern to match NSLocalizedString calls
    # Handles various formats:
    # NSLocalizedString("key", comment: "...")
    # NSLocalizedString("key", bundle: ..., comment: "...")
    # NSLocalizedString("key", tableName: ..., comment: "...")
    pattern = r'NSLocalizedString\s*\(\s*"([^"]+)"(?:\s*,\s*(?:bundle|tableName):\s*[^,]+)*\s*,\s*comment:\s*"[^"]*"\s*\)'
    
    def replacement_func(match):
        nonlocal replacements_made, unmatched_keys
        key = match.group(1)
        
        if key in key_mappings:
            replacements_made += 1
            return key_mappings[key]
        else:
            unmatched_keys.add(key)
            return match.group(0)  # Return original if no mapping found
    
    content = re.sub(pattern, replacement_func, content)
    
    # Also handle simpler cases without bundle/tableName parameters
    simple_pattern = r'NSLocalizedString\s*\(\s*"([^"]+)"\s*,\s*comment:\s*"[^"]*"\s*\)'
    content = re.sub(simple_pattern, replacement_func, content)
    
    if not dry_run and content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    return replacements_made, len(unmatched_keys)

def find_swift_files(directory):
    """Recursively find all Swift files in directory"""
    swift_files = []
    for root, dirs, files in os.walk(directory):
        # Skip common build/cache directories
        dirs[:] = [d for d in dirs if d not in ['.build', 'build', 'DerivedData', '.git', 'Pods']]
        
        for file in files:
            if file.endswith('.swift'):
                swift_files.append(os.path.join(root, file))
    
    return swift_files

def main():
    parser = argparse.ArgumentParser(description='Replace NSLocalizedString with SwiftGen L10n variables')
    parser.add_argument('project_path', help='Path to Swift project directory')
    parser.add_argument('--localizable', '-l', 
                       help='Path to Localizable.strings file (default: project_path/Resources/Localizable.strings)')
    parser.add_argument('--dry-run', '-d', action='store_true', 
                       help='Show what would be changed without making changes')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed output')
    
    args = parser.parse_args()
    
    project_path = Path(args.project_path)
    if not project_path.exists():
        print(f"Error: Project path {project_path} does not exist")
        return 1
    
    # Determine Localizable.strings path
    if args.localizable:
        localizable_path = Path(args.localizable)
    else:
        # Common locations for Localizable.strings
        possible_paths = [
            project_path / "Resources" / "Localizable.strings",
            project_path / "Localizable.strings",
            project_path / "Supporting Files" / "Localizable.strings",
        ]
        
        localizable_path = None
        for path in possible_paths:
            if path.exists():
                localizable_path = path
                break
        
        if not localizable_path:
            print("Error: Could not find Localizable.strings file")
            print("Please specify the path using --localizable option")
            print("Searched in:")
            for path in possible_paths:
                print(f"  - {path}")
            return 1
    
    print(f"Using Localizable.strings: {localizable_path}")
    
    # Parse the localizable strings
    key_mappings = parse_localizable_strings(localizable_path)
    if not key_mappings:
        print("No localizable keys found. Exiting.")
        return 1
    
    # Find all Swift files
    swift_files = find_swift_files(project_path)
    print(f"Found {len(swift_files)} Swift files")
    
    if args.dry_run:
        print("\n--- DRY RUN MODE ---")
    
    total_replacements = 0
    total_unmatched = 0
    files_modified = 0
    
    for file_path in swift_files:
        replacements, unmatched = replace_nslocalizedstring_in_file(file_path, key_mappings, args.dry_run)
        
        if replacements > 0 or (args.verbose and unmatched > 0):
            relative_path = os.path.relpath(file_path, project_path)
            print(f"{relative_path}: {replacements} replacements", end="")
            if unmatched > 0:
                print(f", {unmatched} unmatched keys", end="")
            print()
            
            if replacements > 0:
                files_modified += 1
            
        total_replacements += replacements
        total_unmatched += unmatched
    
    print(f"\nSummary:")
    print(f"  Files processed: {len(swift_files)}")
    print(f"  Files modified: {files_modified}")
    print(f"  Total replacements: {total_replacements}")
    if total_unmatched > 0:
        print(f"  Unmatched keys: {total_unmatched}")
        print(f"  (Keys not found in Localizable.strings or already converted)")
    
    if args.dry_run:
        print("\nRun without --dry-run to apply changes")
    
    return 0

if __name__ == '__main__':
    exit(main())
