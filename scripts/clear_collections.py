#!/usr/bin/env python3
"""
scripts/clear_collections.py

Safe helper to inspect and clear MongoDB collections.

Usage:
  # interactive (will prompt before destructive action)
  python scripts/clear_collections.py --db MozaiksAI --collections WorkflowStats,ChatSessions

  # non-interactive: delete documents (preserve indexes)
  python scripts/clear_collections.py --db MozaiksAI --collections WorkflowStats,ChatSessions --action delete --yes

  # non-interactive: drop collections (removes indexes)
  python scripts/clear_collections.py --db MozaiksAI --collections WorkflowStats,ChatSessions --action drop --yes

Notes:
- The script looks for MONGO_URI in the environment, and falls back to reading it from a local .env file in the repo root if present.
- By default the script performs `delete_many({})` which removes documents but preserves collection indexes. Use `--action drop` to remove the entire collection (including indexes).
- Ensure you have a backup (mongodump or other) if you might need to recover data.

Requires: pymongo (pip install pymongo)
"""

import os
import sys
import argparse
from pathlib import Path
from pymongo import MongoClient


def read_mongo_uri_from_env_or_dotenv(dotenv_path='.env'):
    # Check environment first
    uri = os.environ.get('MONGO_URI')
    if uri:
        return uri
    # Try to read .env
    p = Path(dotenv_path)
    if p.exists():
        with p.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('MONGO_URI='):
                    return line.split('=', 1)[1].strip()
    return None


def confirm(prompt: str) -> bool:
    try:
        resp = input(prompt + ' [y/N]: ').strip().lower()
    except EOFError:
        return False
    return resp in ('y', 'yes')


def main():
    parser = argparse.ArgumentParser(description='Clear MongoDB collections (delete or drop)')
    parser.add_argument('--mongo-uri', help='Mongo URI. If omitted, read from MONGO_URI env or .env')
    parser.add_argument('--db', default='MozaiksAI', help='Database name (default: MozaiksAI)')
    parser.add_argument('--collections', default='WorkflowStats,ChatSessions,GeneralChatSessions,GeneralChatCounters', help='Comma-separated list of collection names (default: WorkflowStats,ChatSessions,GeneralChatSessions,GeneralChatCounters)')
    parser.add_argument('--action', choices=['delete', 'drop'], default='delete', help='delete: delete documents; drop: drop collection')
    parser.add_argument('--yes', '-y', action='store_true', help='Run non-interactively and confirm actions')
    args = parser.parse_args()

    mongo_uri = args.mongo_uri or read_mongo_uri_from_env_or_dotenv()
    if not mongo_uri:
        print('Error: MONGO_URI not found in environment or .env', file=sys.stderr)
        sys.exit(2)

    collections = [c.strip() for c in args.collections.split(',') if c.strip()]
    if not collections:
        print('No collections specified; nothing to do.', file=sys.stderr)
        sys.exit(2)

    print(f'Connecting to MongoDB...')
    client = MongoClient(mongo_uri)
    db = client[args.db]

    print(f'Using DB: {args.db}')

    # Show counts
    counts = {}
    for coll in collections:
        try:
            counts[coll] = db[coll].count_documents({})
        except Exception as e:
            counts[coll] = f'ERROR: {e}'

    print('Current counts:')
    for coll, cnt in counts.items():
        print(f'  {coll}: {cnt}')

    # Confirm
    action_text = 'delete all documents (preserve indexes)' if args.action == 'delete' else 'drop the collection (remove indexes)'
    print('\nRequested action: {} on collections: {}'.format(action_text, ', '.join(collections)))

    if not args.yes:
        ok = confirm('Proceed with the action?')
        if not ok:
            print('Aborted by user.')
            sys.exit(0)

    # Perform action
    for coll in collections:
        print(f'Processing collection: {coll}')
        try:
            if args.action == 'delete':
                res = db[coll].delete_many({})
                print(f'  Deleted {res.deleted_count} documents from {coll}')
            else:
                db[coll].drop()
                print(f'  Dropped collection {coll}')
        except Exception as e:
            print(f'  ERROR processing {coll}: {e}', file=sys.stderr)

    # Show counts after
    print('\nCounts after:')
    for coll in collections:
        try:
            cnt = db[coll].count_documents({})
        except Exception as e:
            cnt = f'ERROR: {e}'
        print(f'  {coll}: {cnt}')

    print('\nDone.')


if __name__ == '__main__':
    main()
