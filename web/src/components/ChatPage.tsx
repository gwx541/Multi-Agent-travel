import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  patchMessage,
  updateConversation,
  appendMessage,
  truncateFrom,
  getPreferences,
  addPreferences,
  recentHistory,
  isPersistentStorageGranted,
  requestPersistentStorage,
  migrateToExternalIfNeeded,
  MEMORY_FILE_HINT,
} from '../lib/localMemory';
import { AuthOverlay } from './AuthOverlay';
import { ConversationDrawer } from './ConversationDrawer';
import { MarkdownContent } from './MarkdownContent';
import { useAuth } from '../hooks/useAuth';
import { useChatStream } from '../hooks/useChatStream';
import { useGeolocation } from '../hooks/useGeolocation';
import { escapeHtml, renderMarkdown } from '../lib/markdown';
import { installLinkInterceptor } from '../lib/openExternal';
import { isNative } from '../lib/native';
import { getApiBase, setApiBase } from '../config';
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
  const { user, showOverlay, login, register, logout } = auth;
  const { location, status: locStatus, detect, detectIfGranted } = useGeolocation();
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
  const [preferences, setPreferences] = useState<string[]>([]);
  const [storageReady, setStorageReady] = useState(true);

  const chatRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    return installLinkInterceptor(el);
  }, []);

  const handleServerSetting = useCallback(() => {
    const current = getApiBase();
    const next = window.prompt(
      '设置后端服务器地址（安卓 App 需填写电脑/服务器的可访问地址，例如 http://192.168.1.10:8000）。留空则使用相对路径。',
      current,
    );
    if (next === null) return;
    setApiBase(next);
    window.location.reload();
  }, []);

  const handleAuthorizeStorage = useCallback(async () => {
    await requestPersistentStorage();
    const granted = await isPersistentStorageGranted();
    setStorageReady(granted);
    if (granted) {
      await migrateToExternalIfNeeded();
      appendSystem(`已开启所有文件访问，记忆保存在 ${MEMORY_FILE_HINT}。`);
    } else {
      appendSystem(
        '请在打开的系统设置页里允许「所有文件访问」，返回后再点一次「存储授权」。',
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleViewMemory = useCallback(() => {
    window.alert(
      preferences.length
        ? `已记住的长期偏好：\n- ${preferences.join('\n- ')}`
        : '暂无长期偏好。聊天中告诉我你的偏好（如「不吃辣」），我会记住并存到本地。',
    );
  }, [preferences]);

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
    void loadConversations();
    void loadHistory(conversationId);
    detectIfGranted();
    void (async () => {
      setPreferences(await getPreferences());
      if (isNative()) {
        const granted = await isPersistentStorageGranted();
        setStorageReady(granted);
        if (granted) {
          await migrateToExternalIfNeeded();
        } else {
          appendSystem(
            `记忆暂存于 App 内部；点右上角「存储授权」开启「所有文件访问」后，` +
              `记忆将保存到 ${MEMORY_FILE_HINT}，卸载不丢、换机可拷贝。`,
          );
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const appendSystem = useCallback((text: string) => {
    setSystemNotes((prev) => [...prev, text]);
  }, []);

  const handleSend = useCallback(
    async (textOverride?: string, replaceMessageId?: number | null) => {
      const text = (textOverride ?? input).trim();
      if (!text) return;

      if (!textOverride) setInput('');

      let cid = conversationId;

      // 编辑并重新生成：先在本地截断目标消息及其之后的所有消息
      if (replaceMessageId != null) {
        const truncCid = await truncateFrom(replaceMessageId);
        if (truncCid) cid = truncCid;
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === replaceMessageId);
          return idx >= 0 ? prev.slice(0, idx) : prev;
        });
      }

      // 发给模型的上下文（在写入本条用户消息之前取，避免重复）
      const history = await recentHistory(cid, 8);
      const prefs = await getPreferences();
      const existingTitle = cid
        ? conversations.find((c) => c.id === cid)?.title || ''
        : '';
      const needTitle = !existingTitle.trim();

      // 持久化用户消息到本地
      const appendedUser = await appendMessage(cid, 'user', text);
      cid = appendedUser.conversationId;
      setConversationId(cid);
      setStoredConversationId(cid);
      setMessages((prev) => [
        ...prev,
        {
          id: appendedUser.id,
          role: 'user',
          content: text,
          html: escapeHtml(text),
        },
      ]);

      await send({
        message: text,
        conversationId: cid,
        location,
        preferences: prefs,
        history,
        needTitle,
        onFinal: async ({ html, rawText, final }) => {
          const appendedAsst = await appendMessage(cid, 'assistant', rawText);
          setMessages((prev) => [
            ...prev,
            { id: appendedAsst.id, role: 'assistant', content: rawText, html },
          ]);
          if (final.new_preferences?.length) {
            await addPreferences(final.new_preferences);
            setPreferences(await getPreferences());
          }
          if (needTitle && final.conversation_title && cid) {
            await updateConversation(cid, { title: final.conversation_title });
          }
          await loadConversations();
        },
        onError: (msg) => appendSystem(`出错了：${msg}`),
        onAborted: () => appendSystem('已停止本次回复'),
      });
    },
    [input, conversationId, location, conversations, send, appendSystem, loadConversations],
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
            <button type="button" onClick={() => void detect(false)} title="获取 GPS 位置">
              定位
            </button>
            <button type="button" onClick={handleViewMemory} title="查看长期记忆">
              记忆
            </button>
            {isNative() && !storageReady && (
              <button
                type="button"
                onClick={() => void handleAuthorizeStorage()}
                title="开启『所有文件访问』以持久保存记忆（卸载不丢/可换机）"
              >
                存储授权
              </button>
            )}
            {isNative() && (
              <button
                type="button"
                onClick={handleServerSetting}
                title="设置后端服务器地址"
              >
                服务器
              </button>
            )}
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
