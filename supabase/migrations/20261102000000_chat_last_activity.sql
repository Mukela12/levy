-- 2 Nov 2026. Run once in the Supabase SQL editor; safe to re-run.
--
-- The recent chats list sorted by when a chat was started, so a chat begun
-- months ago stayed at the bottom however much it was used. One user's main
-- chat (253 messages, started 26 May, used again on 1 Nov) was always last in
-- their list, and they reported it gone on 18 and again on 23 Oct.
-- chat_sessions.updated_at has existed since the first schema, but nothing
-- ever wrote it: on 2 Nov all 379 chats had updated_at equal to created_at.
-- After this runs, updated_at is the time of the chat's newest message, and
-- the list sorts by it (frontend/src/components/chat/use-recent-sessions.ts).

-- 1. Move the chat's updated_at forward whenever a message is saved. A trigger,
--    because messages are saved from three places: the browser
--    (chat-stream-context.tsx), and on the server both the durable run's answer
--    and its repair of a dropped question (chat_persist.py). Security definer,
--    so the update does not depend on the caller's RLS policies or grants.
--    It only moves forward, so it always equals the newest message's
--    created_at, the same rule as the backfill (the repaired question is
--    backdated to when it was asked). Created before the backfill so a message
--    saved while it runs is not missed.
create or replace function public.chat_sessions_touch()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.chat_sessions
     set updated_at = new.created_at
   where id = new.session_id
     and (updated_at is null or updated_at < new.created_at);
  return null;
end $$;
-- Only the trigger calls it.
revoke execute on function public.chat_sessions_touch() from public, anon, authenticated;

drop trigger if exists chat_messages_touch_session on public.chat_messages;
create trigger chat_messages_touch_session
  after insert on public.chat_messages
  for each row execute function public.chat_sessions_touch();

-- 2. Backfill from each chat's newest message. A chat with no messages keeps
--    its creation time.
update public.chat_sessions s
   set updated_at = m.last_at
  from (select session_id, max(created_at) as last_at
          from public.chat_messages
         group by session_id) m
 where s.id = m.session_id
   and (s.updated_at is null or s.updated_at < m.last_at);

-- 3. Check: trigger_installed should be 1, and chats_with_later_activity close
--    to the number of chats that have any messages.
select (select count(*) from pg_trigger where tgname = 'chat_messages_touch_session') as trigger_installed,
       count(*) filter (where updated_at > created_at) as chats_with_later_activity,
       count(*) as chats
  from public.chat_sessions;
