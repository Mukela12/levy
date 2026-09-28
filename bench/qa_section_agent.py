#!/usr/bin/env python3
"""Bounded paid-model QA of the local agent's section-status use.

Uses public corpus only, no sessions/password resets/persistence. All tool
schemas remain visible, but only three read-only corpus handlers can run.
This is NOT full production/web QA and cannot establish current legal status.
"""
import asyncio
import dataclasses
import json
from pathlib import Path
import sys
import time
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.modules.setdefault('weasyprint', types.SimpleNamespace(HTML=None, CSS=None))
from app.services import agent

READ_ONLY = {'search_corpus', 'check_provision_status', 'search_case_law'}
ORIGINAL_REGISTRY = agent.build_tool_registry


async def unavailable(**kwargs):
    return {'result': {'error': 'Not available in this bounded corpus-only QA run. '
                       'Do not imply external verification or successful execution.'}}


def registry(**kwargs):
    return {name: tool if name in READ_ONLY else dataclasses.replace(tool, handler=unavailable)
            for name, tool in ORIGINAL_REGISTRY(**kwargs).items()}


async def main():
    path = ROOT / 'bench/results/2026-09-28-section-agent-qa.json'
    if path.exists():
        raise SystemExit('QA output exists; refusing an accidental paid rerun')
    results = []
    settings = agent.get_settings().model_copy(update={
        'agent_max_iterations': 5, 'agent_max_output_tokens': 4096,
    })
    questions = [
        ('immigration-24', 'Can I rely on section 24 of the Immigration and Deportation Act 2010 for a business permit? Please explain briefly and cite the relevant amendment if it changed.'),
        ('penal-69', 'Is section 69 of the Zambian Penal Code still an offence I can be charged under? Please verify the section status and keep the answer brief.'),
    ]
    with patch.object(agent, 'build_tool_registry', registry), patch.object(agent, 'get_settings', lambda: settings):
        for qid, question in questions:
            record = {'id': qid, 'question': question, 'answer': '', 'events': [],
                      'condition': 'local agent; full schemas; corpus/status tools only; max 5 iterations, 4096 output tokens per call'}
            started = time.monotonic()
            try:
                async with asyncio.timeout(240):
                    async for event in agent.run_agent(user_query=question):
                        if event['type'] == 'token':
                            record['answer'] += event.get('content', '')
                        elif event['type'] in {'tool_call', 'tool_result', 'done', 'error', 'citation_audit'}:
                            record['events'].append(event)
                            if event['type'] in {'tool_call', 'error', 'done'}:
                                print(qid, event['type'], event.get('name', event.get('model', '')), flush=True)
            except Exception as e:
                record['failure'] = type(e).__name__
            record['seconds'] = round(time.monotonic() - started, 2)
            results.append(record)
            path.write_text(json.dumps(results, indent=2))
            if record.get('failure') or any(e['type'] == 'error' for e in record['events']):
                break
    print('Saved', path)


if __name__ == '__main__':
    asyncio.run(main())
