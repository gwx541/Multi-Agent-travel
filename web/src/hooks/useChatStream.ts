import { useCallback, useRef, useState } from 'react';
import { streamChat } from '../api/chat';
import { linkifyPois } from '../lib/poi';
import { renderMarkdown } from '../lib/markdown';
import type { ChatLocation, FinalPayload } from '../types';

export interface TypingState {
  visible: boolean;
  label: string;
}

export function useChatStream() {
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState<TypingState>({
    visible: false,
    label: '小旅正在思考…',
  });
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(
    async (opts: {
      message: string;
      conversationId?: string | null;
      location?: ChatLocation | null;
      replaceMessageId?: number | null;
      onFinal: (payload: {
        html: string;
        rawText: string;
        final: FinalPayload;
      }) => void;
      onError: (message: string) => void;
      onAborted: () => void;
    }) => {
      if (busy) {
        stop();
        return;
      }

      setBusy(true);
      setTyping({ visible: true, label: '小旅正在思考…' });
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        await streamChat(
          {
            message: opts.message,
            conversation_id: opts.conversationId,
            location: opts.location,
            replace_message_id: opts.replaceMessageId,
          },
          {
            onEvent: (type, payload) => {
              if (type === 'agent_start') {
                const agent = payload.agent as string | undefined;
                if (agent && agent !== 'testing_agent') {
                  setTyping({
                    visible: true,
                    label: `小旅正在调用 ${agent.replace('_agent', '')}…`,
                  });
                }
              } else if (type === 'agent_end') {
                const agent = payload.agent as string | undefined;
                if (agent && agent !== 'testing_agent') {
                  setTyping({
                    visible: true,
                    label: `小旅正在整理 ${agent.replace('_agent', '')} 的结果…`,
                  });
                }
              } else if (type === 'final') {
                setTyping({ visible: false, label: '' });
                const final = payload as unknown as FinalPayload;
                const ctx = {
                  location: final.location,
                  location_info: final.location_info,
                };
                const pois = Array.isArray(final.pois) ? final.pois : [];
                let html = renderMarkdown(final.text || '');
                html = linkifyPois(html, pois, ctx);
                opts.onFinal({
                  html,
                  rawText: final.text || '',
                  final,
                });
              } else if (type === 'error') {
                setTyping({ visible: false, label: '' });
                opts.onError(String(payload.text || '后端异常'));
              }
            },
          },
          ctrl.signal,
        );
      } catch (e) {
        setTyping({ visible: false, label: '' });
        if (e instanceof DOMException && e.name === 'AbortError') {
          opts.onAborted();
        } else {
          opts.onError(e instanceof Error ? e.message : '网络错误');
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
        setTyping({ visible: false, label: '' });
      }
    },
    [busy, stop],
  );

  return { busy, typing, send, stop };
}
