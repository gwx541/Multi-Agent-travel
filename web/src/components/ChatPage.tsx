import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  patchMessage,
  updateConversation,
} from '../api/conversations';
import { AuthOverlay } from './AuthOverlay';
import { ConversationDrawer } from './ConversationDrawer';
import { MarkdownContent } from './MarkdownContent';
import { useAuth } from '../hooks/useAuth';
import { useChatStream } from '../hooks/useChatStream';
import { useGeolocation } from '../hooks/useGeolocation';
import { escapeHtml, renderMarkdown } from '../lib/markdown';
import {
  clearStoredConversationId,
  getStoredConversationId,
  setStoredConversationId,
} from '../lib/storage';
import type { ChatMessage, Conversation, User } from '../types';
import './ChatPage.css';

const WELCOME_HTML =
  '你好呀～我是小旅，专注<strong>行程规划</strong>与<strong>火车票、机票、酒店</strong>等票务协助 ✨<br>告诉我目的地、时间和预算，我帮你排行程、查余票～';

interface Props {
  auth: ReturnType<typeof useAuth>;
}

export function ChatPage({ auth }: Props) {
  const { user, showOverlay, login, register, logout, handleSessionExpired } =
    auth;
  const { location, status: locStatus, detect } = useGeolocation();
  const { busy, typing, send, stop } = useChatStream();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(
    getStoredConversationId,
  );
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: '', html: WELCOME_HTML },
  ]);
  const [systemNotes, setSystemNotes] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState('');

  const chatRef = useRef<HTMLDivElement>(null);
  const pendingUserIdx = useRef<number | null>(null);

  const convTitle =
    conversations.find((c) => c.id === conversationId)?.title ||
    (conversationId ? '未命名对话' : '小旅 · 行程规划与票务');

  const scrollToBottom = useCallback(() => {
    const el = chatRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, systemNotes, typing, scrollToBottom]);

  const loadConversations = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations(list);
      const stored = getStoredConversationId();
      const existing = list.find((c) => c.id === stored);
      if (existing) setConversationId(existing.id);
      else if (list.length) {
        setConversationId(list[0].id);
        setStoredConversationId(list[0].id);
      }
    } catch {
      /* silent before auth */
    }
  }, []);

  const loadHistory = useCallback(async (cid?: string | null) => {
    try {
      const data = await listMessages(cid);
      const msgs = data.messages || [];
      if (!msgs.length) {
        setMessages([{ role: 'assistant', content: '', html: WELCOME_HTML }]);
      } else {
        setMessages(
          msgs.map((m) => ({
            id: m.id,
            role: m.role as ChatMessage['role'],
            content: m.content,
            html:
              m.role === 'assistant'
                ? renderMarkdown(m.content)
                : escapeHtml(m.content),
          })),
        );
      }
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
        setStoredConversationId(data.conversation_id);
      }
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    if (auth.loading) return;
    if (showOverlay) return;
    void loadConversations();
    void loadHistory(conversationId);
    void detect(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.loading, showOverlay]);

  const appendSystem = useCallback((text: string) => {
    setSystemNotes((prev) => [...prev, text]);
  }, []);

  const handleSend = useCallback(
    async (textOverride?: string, replaceMessageId?: number | null) => {
      const text = (textOverride ?? input).trim();
      if (!text) return;

      if (!textOverride) setInput('');

      if (replaceMessageId == null) {
        setMessages((prev) => {
          pendingUserIdx.current = prev.length;
          return [
            ...prev,
            { role: 'user', content: text, html: escapeHtml(text) },
          ];
        });
      }

      await send({
        message: text,
        conversationId,
        location,
        replaceMessageId,
        onFinal: ({ html, rawText, final }) => {
          setMessages((prev) => {
            const next = [...prev];
            const ids = final.message_ids;
            if (ids?.user != null && pendingUserIdx.current != null) {
              const idx = pendingUserIdx.current;
              if (next[idx]) next[idx] = { ...next[idx], id: ids.user };
            }
            next.push({
              id: ids?.assistant,
              role: 'assistant',
              content: rawText,
              html,
            });
            return next;
          });
          pendingUserIdx.current = null;

          if (final.conversation_id) {
            const cid = final.conversation_id;
            setConversationId(cid);
            setStoredConversationId(cid);
            if (final.conversation_title) {
              setConversations((prev) => {
                const found = prev.find((c) => c.id === cid);
                if (found) {
                  return prev.map((c) =>
                    c.id === cid
                      ? { ...c, title: final.conversation_title! }
                      : c,
                  );
                }
                return [
                  {
                    id: cid,
                    title: final.conversation_title!,
                    created_at: null,
                    updated_at: new Date().toISOString(),
                    archived: false,
                    message_count: 0,
                  },
                  ...prev,
                ];
              });
            }
            void loadConversations();
          }
        },
        onError: (msg) => {
          if (msg.includes('登录已失效')) handleSessionExpired();
          appendSystem(`出错了：${msg}`);
        },
        onAborted: () => appendSystem('已停止本次回复'),
      });
    },
    [
      input,
      conversationId,
      location,
      messages.length,
      send,
      appendSystem,
      handleSessionExpired,
      loadConversations,
    ],
  );

  const handleCreateConversation = async () => {
    try {
      const conv = await createConversation();
      setConversations((prev) => [conv, ...prev]);
      setConversationId(conv.id);
      setStoredConversationId(conv.id);
      setMessages([
        {
          role: 'assistant',
          content: '新对话开始啦～有什么旅行需求都可以问我。',
          html: '新对话开始啦～有什么旅行需求都可以问我。',
        },
      ]);
      setDrawerOpen(false);
    } catch (e) {
      appendSystem(
        `新建对话失败：${e instanceof Error ? e.message : '未知错误'}`,
      );
    }
  };

  const handleSelectConversation = async (id: string) => {
    setConversationId(id);
    setStoredConversationId(id);
    await loadHistory(id);
    setDrawerOpen(false);
  };

  const handleRename = async (conv: Conversation) => {
    const title = window.prompt('重命名对话', conv.title || '');
    if (title == null) return;
    try {
      await updateConversation(conv.id, { title: title.trim() || '未命名对话' });
      await loadConversations();
    } catch (e) {
      appendSystem(`重命名失败：${e instanceof Error ? e.message : '未知错误'}`);
    }
  };

  const handleDelete = async (conv: Conversation) => {
    if (!window.confirm(`确定删除「${conv.title || '未命名对话'}」？`)) return;
    try {
      await deleteConversation(conv.id);
      const list = await listConversations();
      setConversations(list);
      if (conv.id === conversationId) {
        const next = list[0]?.id ?? null;
        setConversationId(next);
        if (next) {
          setStoredConversationId(next);
          await loadHistory(next);
        } else {
          clearStoredConversationId();
          setMessages([{ role: 'assistant', content: '', html: WELCOME_HTML }]);
        }
      }
    } catch (e) {
      appendSystem(`删除失败：${e instanceof Error ? e.message : '未知错误'}`);
    }
  };

  const lastUserMessageId = [...messages]
    .reverse()
    .find((m) => m.role === 'user' && m.id != null)?.id;

  const startEdit = (msg: ChatMessage) => {
    if (busy || msg.id == null) return;
    setEditingId(msg.id);
    setEditDraft(msg.content);
  };

  const saveEditOnly = async () => {
    if (editingId == null) return;
    const content = editDraft.trim();
    if (!content) return;
    try {
      await patchMessage(editingId, content);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === editingId
            ? { ...m, content, html: escapeHtml(content) }
            : m,
        ),
      );
      setEditingId(null);
    } catch (e) {
      appendSystem(`保存失败：${e instanceof Error ? e.message : '未知错误'}`);
    }
  };

  const saveEditAndRegenerate = async () => {
    if (editingId == null) return;
    const content = editDraft.trim();
    if (!content) return;
    const id = editingId;
    setEditingId(null);
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === id);
      if (idx < 0) return prev;
      pendingUserIdx.current = idx;
      const next = prev.slice(0, idx + 1);
      next[idx] = {
        ...next[idx],
        content,
        html: escapeHtml(content),
      };
      return next;
    });
    await handleSend(content, id);
  };

  const onAuthSuccess = async (u: User, mode: 'login' | 'register') => {
    clearStoredConversationId();
    setConversationId(null);
    await loadConversations();
    await loadHistory(null);
    appendSystem(
      `已${mode === 'login' ? '登录' : '注册'}为 ${u.email}，记忆与行程将绑定当前账户。`,
    );
  };

  return (
    <div className={`stage${busy ? ' busy' : ''}`}>
      <div className="phone">
        <div className="notch" />
        {showOverlay && (
          <AuthOverlay
            onLogin={async (email, password) => {
              const u = await login(email, password);
              await onAuthSuccess(u, 'login');
            }}
            onRegister={async (email, password) => {
              const u = await register(email, password);
              await onAuthSuccess(u, 'register');
            }}
          />
        )}
        <ConversationDrawer
          open={drawerOpen}
          conversations={conversations}
          currentId={conversationId}
          onClose={() => setDrawerOpen(false)}
          onSelect={(id) => void handleSelectConversation(id)}
          onCreate={() => void handleCreateConversation()}
          onRename={(c) => void handleRename(c)}
          onDelete={(c) => void handleDelete(c)}
        />
        <header>
          <button
            type="button"
            className="hamburger"
            onClick={() => setDrawerOpen(true)}
            aria-label="打开对话列表"
          >
            ☰
          </button>
          <div className="avatar">旅</div>
          <div className="header-text">
            <div className="title">{convTitle}</div>
            <div className="sub">Multi-Agent 智能旅行助手</div>
          </div>
          <div className="toolbar">
            {user && (
              <span className="user-badge" title={user.email}>
                {user.email}
              </span>
            )}
            <button type="button" onClick={() => void detect(false)}>
              定位
            </button>
            {user && (
              <button type="button" onClick={logout}>
                退出
              </button>
            )}
          </div>
        </header>
        <div className="loc-bar">
          <span className="loc-pill">GPS</span>
          {locStatus}
        </div>
        <div className="chat" ref={chatRef}>
          {messages.map((msg, i) => (
            <div
              key={msg.id ?? `msg-${i}`}
              className={`msg ${msg.role === 'user' ? 'user' : 'bot'}`}
            >
              {msg.agentName && (
                <span className={`agent-tag ${msg.agentName}`}>
                  {msg.agentName}
                </span>
              )}
              {editingId === msg.id ? (
                <div className="edit-box">
                  <textarea
                    value={editDraft}
                    onChange={(e) => setEditDraft(e.target.value)}
                    rows={3}
                  />
                  <div className="edit-actions">
                    <button type="button" onClick={() => setEditingId(null)}>
                      取消
                    </button>
                    <button type="button" onClick={() => void saveEditOnly()}>
                      仅保存
                    </button>
                    <button
                      type="button"
                      className="primary"
                      onClick={() => void saveEditAndRegenerate()}
                    >
                      重新生成
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <MarkdownContent html={msg.html || ''} />
                  {msg.role === 'user' &&
                    msg.id === lastUserMessageId &&
                    !busy && (
                      <div className="msg-actions">
                        <button type="button" onClick={() => startEdit(msg)}>
                          ✎ 编辑
                        </button>
                      </div>
                    )}
                </>
              )}
            </div>
          ))}
          {systemNotes.map((note, i) => (
            <div key={`sys-${i}`} className="msg system">
              {note}
            </div>
          ))}
          {typing.visible && (
            <div className="typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
              {typing.label}
            </div>
          )}
        </div>
        <footer>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="说说你想去哪、什么时候、预算多少…"
            disabled={showOverlay}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !busy && !showOverlay) {
                void handleSend();
              }
            }}
          />
          <button
            type="button"
            className={busy ? 'stop' : ''}
            onClick={() => (busy ? stop() : void handleSend())}
            disabled={showOverlay}
          >
            {busy ? '停止' : '发送'}
          </button>
        </footer>
      </div>
    </div>
  );
}
