#!/usr/bin/env python3
"""Isolated local FTS regression test; never connects to Supabase.

No local pgvector extension is required. Vector type/calculation is replaced
with a nullable array/NULL in this sandbox ONLY. This tests SQL ranking and
visibility, not vector distance or production performance.
"""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import time
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DB = 'levy_hybrid_qa_20260928'


def sql(statement, db=DB):
    return subprocess.check_output(
        ['psql', '-X', '-h', '/tmp', '-d', db, '-At', '-v', 'ON_ERROR_STOP=1', '-c', statement],
        text=True).strip()


def copy(table, columns, rows):
    # File COPY avoids psql treating a standalone \\. in legal text as EOF.
    with tempfile.NamedTemporaryFile(mode='w+', newline='', suffix='.csv') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
        f.flush()
        sql(f"COPY {table} ({columns}) FROM {quote(f.name)} WITH (FORMAT csv)")


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def sandbox_migration(path):
    text = path.read_text().replace('vector(768)', 'real[]')
    text = text.replace('(1 - (lc.embedding <=> query_embedding))::FLOAT', 'NULL::FLOAT')
    return re.sub(r'^(REVOKE|GRANT).*;$', '', text, flags=re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if sql(f'SELECT 1 FROM pg_database WHERE datname={quote(DB)}', 'postgres'):
        raise SystemExit(f'{DB} already exists; refusing to overwrite it')
    sql(f'CREATE DATABASE {DB}', 'postgres')
    sql('''CREATE TABLE legal_documents(id uuid PRIMARY KEY, is_global boolean, owner_id uuid);
           CREATE TABLE legal_chunks(id uuid PRIMARY KEY, document_id uuid REFERENCES legal_documents,
           content text, metadata jsonb, page_start int, page_end int, embedding real[]);''')
    # Only public documents from the pre-existing snapshot are imported.
    docs = json.loads(Path(str(args.corpus) + '.docs.json').read_text())
    public = {d['id'] for d in docs.values() if d.get('is_global') is True}
    copy('legal_documents', 'id,is_global', ((d, True) for d in public))

    def rows():
        with args.corpus.open() as f:
            for line in f:
                r = json.loads(line)
                if r['d'] in public:
                    yield r['id'], r['d'], r['c'], json.dumps({'act_name': r['act'], 'section_number': r['s']})
    copy('legal_chunks', 'id,document_id,content,metadata', rows())
    for name in ['20260928000000_keyword_search.sql', '20260928010000_keyword_search_v2.sql']:
        sql(sandbox_migration(ROOT / 'supabase/migrations' / name))
    sql('ANALYZE legal_documents; ANALYZE legal_chunks; ANALYZE legal_chunk_lexemes;')
    report = {'database': DB, 'scope': 'local public snapshot, vector calculation stubbed',
              'chunks': int(sql('SELECT count(*) FROM legal_chunks')), 'questions': []}
    gold = json.loads((ROOT / 'backend/tests/gold_qa.json').read_text())
    for q in gold:
        if not q.get('expected_act'):
            continue
        record = {'id': q['id']}
        for version, fn in [('v1', 'search_legal_chunks_keyword'), ('v2', 'search_legal_chunks_keyword_v2')]:
            start = time.monotonic()
            data = sql(f'SELECT coalesce(json_agg(r),\'[]\') FROM (SELECT id,keyword_rank FROM {fn}({quote(q["question"])})) r')
            record[version] = {'seconds': round(time.monotonic() - start, 4), 'rows': json.loads(data)}
        a, b = [{r['id'] for r in record[v]['rows']} for v in ['v1', 'v2']]
        record['overlap'] = len(a & b) / max(len(a), 1)
        # Equal-score boundary ties may select another ID; changed ranking
        # scores or a missing result must not silently pass as equivalent.
        assert [round(r['keyword_rank'], 10) for r in record['v1']['rows']] == [
            round(r['keyword_rank'], 10) for r in record['v2']['rows']], q['id']
        report['questions'].append(record)
        print(q['id'], record['v1']['seconds'], record['v2']['seconds'], 'overlap', record['overlap'], flush=True)
    # Transactional private fixtures: lexical ranking must not expose foreign uploads.
    checks = sql('''BEGIN;
      INSERT INTO legal_documents VALUES
      ('00000000-0000-0000-0000-000000000001',false,'00000000-0000-0000-0000-000000000010'),
      ('00000000-0000-0000-0000-000000000002',false,'00000000-0000-0000-0000-000000000020');
      INSERT INTO legal_chunks(id,document_id,content) VALUES
      ('00000000-0000-0000-0000-000000000101','00000000-0000-0000-0000-000000000001','zzfixturequartz'),
      ('00000000-0000-0000-0000-000000000102','00000000-0000-0000-0000-000000000002','zzfixturequartz');
      SELECT 'anonymous='||count(*) FROM search_legal_chunks_keyword_v2('zzfixturequartz');
      SELECT 'owner='||count(*) FROM search_legal_chunks_keyword_v2('zzfixturequartz',NULL,30,'00000000-0000-0000-0000-000000000010');
      SELECT 'attached='||count(*) FROM search_legal_chunks_keyword_v2('zzfixturequartz',NULL,30,NULL,ARRAY['00000000-0000-0000-0000-000000000002']::uuid[]);
      SELECT 'empty='||count(*) FROM search_legal_chunks_keyword_v2('');
      SELECT 'zero='||count(*) FROM search_legal_chunks_keyword_v2('employment',NULL,0);
      ROLLBACK;''')
    for expected in ['anonymous=0', 'owner=1', 'attached=1', 'empty=0', 'zero=0']:
        assert expected in checks.splitlines(), checks
    report['scope_checks'] = checks.splitlines()
    args.out.write_text(json.dumps(report, indent=2))
    print('PASSED: visibility, empty query and zero count; report:', args.out)


if __name__ == '__main__':
    main()
