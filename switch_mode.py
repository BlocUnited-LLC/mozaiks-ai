#!/usr/bin/env python3
"""
Open Source Distribution Preparation Script

This script demonstrates how easy it is to prepare the codebase for open source distribution
by switching the budget capability mode.
"""

import os
import sys
from pathlib import Path

def switch_to_open_source_mode():
    """Switch the application to open source mode."""
    config_path = Path(__file__).parent / "core" / "capabilities" / "config.py"
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return False
    
    # Read current config
    with open(config_path, 'r') as f:
        content = f.read()
    
    # Update to open source mode
    content = content.replace(
        'OPEN_SOURCE_MODE = False',
        'OPEN_SOURCE_MODE = True'
    )
    
    # Write updated config
    with open(config_path, 'w') as f:
        f.write(content)
    
    print("✅ Successfully switched to open source mode!")
    print("📋 Changes made:")
    print("   - OPEN_SOURCE_MODE = True")
    print("   - Budget capability will use 'opensource' mode automatically")
    print("   - All commercial features (free trials, token billing) are disabled")
    print("   - Users get unlimited usage without budget restrictions")
    
    return True

def switch_to_commercial_mode():
    """Switch the application to commercial mode."""
    config_path = Path(__file__).parent / "core" / "capabilities" / "config.py"
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return False
    
    # Read current config
    with open(config_path, 'r') as f:
        content = f.read()
    
    # Update to commercial mode
    content = content.replace(
        'OPEN_SOURCE_MODE = True',
        'OPEN_SOURCE_MODE = False'
    )
    content = content.replace(
        'BUDGET_MODE = "testing"',
        'BUDGET_MODE = "commercial"'
    )
    
    # Write updated config
    with open(config_path, 'w') as f:
        f.write(content)
    
    print("✅ Successfully switched to commercial mode!")
    print("📋 Changes made:")
    print("   - OPEN_SOURCE_MODE = False")
    print("   - BUDGET_MODE = 'commercial'")
    print("   - Free trials and token billing are enabled")
    print("   - Full TokenManager functionality is active")
    
    return True

def show_current_mode():
    """Show the current configuration mode."""
    project_root = Path(__file__).parent
    
    try:
        # Add the project root to Python path
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        # Direct import from config file
        config_path = project_root / "core" / "capabilities" / "config.py"
        if not config_path.exists():
            print(f"❌ Config file not found: {config_path}")
            return
        
        # Read and parse config directly
        config_content = {}
        with open(config_path, 'r') as f:
            exec(f.read(), config_content)
        
        open_source_mode = config_content.get('OPEN_SOURCE_MODE', False)
        budget_mode = config_content.get('BUDGET_MODE', 'testing')
        
        # Determine effective mode
        if open_source_mode:
            effective_mode = "opensource"
        else:
            effective_mode = budget_mode
        
        print(f"🔍 Current Mode: {effective_mode}")
        print(f"📦 Open Source: {'Yes' if open_source_mode else 'No'}")
        print(f"⚙️  Budget Mode Setting: {budget_mode}")
        
        if effective_mode == "opensource":
            print("   → Unlimited usage, no commercial restrictions")
        elif effective_mode == "commercial":
            print("   → Full TokenManager with free trials and billing")
        elif effective_mode == "testing":
            print("   → Development mode without real API calls")
            
    except Exception as e:
        print(f"❌ Could not read configuration: {e}")
        print(f"   Make sure the config file exists at: {project_root / 'core' / 'capabilities' / 'config.py'}")

if __name__ == "__main__":
    print("🔧 Budget Capability Mode Switcher")
    print("=" * 40)
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python switch_mode.py status     - Show current mode")
        print("  python switch_mode.py opensource - Switch to open source mode")
        print("  python switch_mode.py commercial - Switch to commercial mode")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_current_mode()
    elif command == "opensource":
        switch_to_open_source_mode()
    elif command == "commercial":
        switch_to_commercial_mode()
    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
