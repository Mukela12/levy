import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.chat_titles import clean_title, name_first_exchange


class FakeDB:
    def __init__(self, title='How do employment contracts work?', turns=None):
        self.title = title
        self.turns = turns or [dict(role='user', content='How do employment contracts work?'), dict(role='assistant', content='Bring your contract for review.')]
        self.updates = []

    def table(self, name):
        db = self
        class Query:
            payload = None
            def select(self, *args): return self
            def eq(self, *args): return self
            def limit(self, *args): return self
            def order(self, *args): return self
            def update(self, payload): self.payload = payload; return self
            def execute(self):
                if self.payload:
                    db.updates.append(self.payload)
                    return SimpleNamespace(data=[self.payload])
                return SimpleNamespace(data=[{'title': db.title}] if name == 'chat_sessions' else db.turns)
        return Query()


class TitlesTest(unittest.IsolatedAsyncioTestCase):
    def test_validation(self):
        self.assertEqual(clean_title('"Employment contract review"'), 'Employment contract review')
        for invalid in ['', 'x' * 65, 'https://example.com', '<script>', 'one two three four five six seven eight nine']:
            self.assertIsNone(clean_title(invalid))

    async def test_names_first_exchange_with_small_budget(self):
        db = FakeDB()
        client = AsyncMock()
        client.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(type='text', text='Employment contract review')])
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch('app.services.chat_titles.get_db', return_value=db), patch('app.services.chat_titles.get_settings', return_value=SimpleNamespace(anthropic_api_key='test-only')), patch('app.services.chat_titles.anthropic.AsyncAnthropic', return_value=context):
            self.assertEqual(await name_first_exchange('session', 'owner'), 'Employment contract review')
        self.assertEqual(db.updates, [{'title': 'Employment contract review'}])
        self.assertEqual(client.messages.create.call_args.kwargs['max_tokens'], 40)

    async def test_manual_title_preserved(self):
        db = FakeDB(title='My chosen title')
        with patch('app.services.chat_titles.get_db', return_value=db), patch('app.services.chat_titles.anthropic.AsyncAnthropic') as provider:
            self.assertIsNone(await name_first_exchange('session', 'owner'))
            provider.assert_not_called()
        self.assertEqual(db.updates, [])

    async def test_later_turns_not_renamed(self):
        db = FakeDB(turns=[dict(role='user'), dict(role='assistant'), dict(role='user')])
        with patch('app.services.chat_titles.get_db', return_value=db), patch('app.services.chat_titles.anthropic.AsyncAnthropic') as provider:
            self.assertIsNone(await name_first_exchange('session', 'owner'))
            provider.assert_not_called()

    async def test_provider_failure_keeps_provisional_title(self):
        db = FakeDB()
        with patch('app.services.chat_titles.get_db', return_value=db), patch('app.services.chat_titles.get_settings', return_value=SimpleNamespace(anthropic_api_key='test-only')), patch('app.services.chat_titles.anthropic.AsyncAnthropic', side_effect=RuntimeError('unavailable')):
            self.assertIsNone(await name_first_exchange('session', 'owner'))
        self.assertEqual(db.updates, [])


if __name__ == '__main__':
    unittest.main()
