"""
Remove backup files from Generator workflow after verifying hooks refactor.
"""
from pathlib import Path
import sys

# Path to Generator workflow
GENERATOR_DIR = Path(__file__).parent.parent / "workflows" / "Generator"

def main():
    print("Searching for backup files in Generator workflow...")
    
    backup_patterns = [
        "agents.json.backup",
        "agents.json.backup2",
        "agents.json.backup3",
        "agents.json.backup4",
        "agents.json.backup5",
    ]
    
    found_backups = []
    
    for pattern in backup_patterns:
        backup_path = GENERATOR_DIR / pattern
        if backup_path.exists():
            found_backups.append(backup_path)
    
    if not found_backups:
        print("✓ No backup files found - already clean")
        return
    
    print(f"\nFound {len(found_backups)} backup file(s):")
    for backup in found_backups:
        size_kb = backup.stat().st_size / 1024
        print(f"  - {backup.name} ({size_kb:.1f} KB)")
    
    # Confirm deletion
    print("\n⚠️  WARNING: This will permanently delete these backup files.")
    response = input("Continue? (yes/no): ").strip().lower()
    
    if response != "yes":
        print("❌ Deletion cancelled")
        sys.exit(0)
    
    # Delete the files
    deleted_count = 0
    for backup in found_backups:
        try:
            backup.unlink()
            print(f"✓ Deleted {backup.name}")
            deleted_count += 1
        except Exception as e:
            print(f"❌ Failed to delete {backup.name}: {e}")
    
    print(f"\n✅ Successfully deleted {deleted_count}/{len(found_backups)} backup file(s)")

if __name__ == "__main__":
    main()
