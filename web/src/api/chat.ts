import { authHeaders, getToken } from './client';
import { apiUrl } from '../config';
import type { ChatLocation, ChatSSEEventType, FinalPayload } from '../types';

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  location?: ChatLocation | null;
  replace_message_id?: number | null;
  preferences?: string[];
  history?: { role: string; content: string }[];
  need_title?: boolean;
}

export interface SSEHandler {
  onEvent: (type: ChatSSEEventType, payload: Record<string, unknown>) => void;
}

export async function streamChat(
  req: ChatRequest,
  handler: SSEHandler,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(apiUrl('/api/chat'), {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      message: req.message,
      conversation_id: req.conversation_id ?? undefined,
      location: req.location ?? undefined,
      preferences: req.preferences ?? undefined,
      history: req.history ?? undefined,
      need_title: req.need_title ?? undefined,
    }),
    signal,
  });

  if (res.status === 401 && getToken()) {
    throw new Error('登录已失效，请重新登录');
  }
  if (!res.ok || !res.body) {
    throw new Error(`请求失败 ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let currentEvent: ChatSSEEventType | '' = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() || '';
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim() as ChatSSEEventType;
      } else if (line.startsWith('data:')) {
        const dataStr = line.slice(5).trim();
        if (!dataStr || !currentEvent) continue;
        let payload: Record<string, unknown> = {};
        try {
          payload = JSON.parse(dataStr) as Record<string, unknown>;
        } catch {
          /* ignore malformed chunk */
        }
        handler.onEvent(currentEvent, payload);
      }
    }
  }
}

export type { FinalPayload };
