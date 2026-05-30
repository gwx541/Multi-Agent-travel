import { apiFetch, authHeaders } from './client';
import type { Conversation, Message } from '../types';

export async function listConversations(): Promise<Conversation[]> {
  const data = await apiFetch<{ conversations: Conversation[] }>(
    '/api/conversations',
    { headers: authHeaders() },
  );
  return data.conversations ?? [];
}

export async function createConversation(
  title?: string,
): Promise<Conversation> {
  return apiFetch<Conversation>('/api/conversations', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(title ? { title } : {}),
  });
}

export async function updateConversation(
  id: string,
  patch: { title?: string; archived?: boolean },
): Promise<Conversation> {
  return apiFetch<Conversation>(`/api/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify(patch),
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await apiFetch<{ ok: boolean }>(
    `/api/conversations/${encodeURIComponent(id)}`,
    { method: 'DELETE', headers: authHeaders() },
  );
}

export async function listMessages(
  conversationId?: string | null,
): Promise<{ messages: Message[]; conversation_id?: string }> {
  const url = conversationId
    ? `/api/messages?conversation_id=${encodeURIComponent(conversationId)}`
    : '/api/messages';
  return apiFetch(url, { headers: authHeaders() });
}

export async function patchMessage(
  messageId: number,
  content: string,
): Promise<void> {
  await apiFetch(`/api/messages/${messageId}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ content }),
  });
}
