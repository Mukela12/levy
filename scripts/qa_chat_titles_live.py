"""Opt-in real-provider title QA. Retains only synthetic QA-account fixtures.

Run from the integration checkout with PYTHONPATH=backend. Load credentials from
an existing environment before running; this script never prints credentials.
"""
import argparse
import asyncio
import json
from uuid import uuid4

from app.db.supabase import get_db
from app.services.chat_titles import name_first_exchange


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-live', action='store_true')
    args = parser.parse_args()
    if not args.run_live:
        raise SystemExit('Requires --run-live; creates a synthetic fixture and makes one naming call.')
    db = get_db()
    source = db.table('chat_sessions').select('user_id').eq('id', '0d6a1947-ec18-4d0c-8778-174cbe2aec8c').single().execute().data
    owner = source['user_id']
    user = db.auth.admin.get_user_by_id(owner).user
    if user.email != 'levy-qa-canopy-20260914@levylegal.ai' or not user.user_metadata.get('is_qa'):
        raise SystemExit('Refusing: fixture owner is not the dedicated QA account.')
    sid = str(uuid4())
    question = 'QA: How should I organise documents for a first lawyer meeting?'
    provisional = question[:57] + '...'
    db.table('chat_sessions').insert({'id': sid, 'user_id': owner, 'title': provisional}).execute()
    for role, content in [('user', question), ('assistant', 'For this fictional QA exercise, group the contract, pay records and correspondence into separate folders.')]:
        db.table('chat_messages').insert({'session_id': sid, 'role': role, 'content': content}).execute()
    title = await name_first_exchange(sid, owner)
    saved = db.table('chat_sessions').select('title').eq('id', sid).single().execute().data['title']
    print(json.dumps({'session_id': sid, 'generated_title': title, 'persisted': bool(title and saved == title)}))
    if not title or title == provisional or saved != title:
        raise SystemExit('Naming did not complete; synthetic fixture retained for inspection.')
    # A user rename is kept even when the naming task is invoked again.
    chosen = 'QA manually named meeting notes'
    db.table('chat_sessions').update({'title': chosen}).eq('id', sid).eq('user_id', owner).execute()
    repeated = await name_first_exchange(sid, owner)
    saved = db.table('chat_sessions').select('title').eq('id', sid).single().execute().data['title']
    if repeated is not None or saved != chosen:
        raise SystemExit('Manual rename preservation failed.')
    print('PASS: real generation, database persistence and manual rename preservation.')


if __name__ == '__main__':
    asyncio.run(main())
