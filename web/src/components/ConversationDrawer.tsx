import type { Conversation } from '../types';
import './ConversationDrawer.css';

interface Props {
  open: boolean;
  conversations: Conversation[];
  currentId: string | null;
  onClose: () => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (conv: Conversation) => void;
  onDelete: (conv: Conversation) => void;
}

export function ConversationDrawer({
  open,
  conversations,
  currentId,
  onClose,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: Props) {
  return (
    <>
      <div
        className={`drawer-backdrop${open ? ' show' : ''}`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside className={`drawer${open ? ' open' : ''}`}>
        <div className="drawer-head">
          <span>对话列表</span>
          <button type="button" onClick={onCreate}>
            + 新对话
          </button>
        </div>
        <ul className="conv-list">
          {!conversations.length ? (
            <li className="conv-empty">还没有任何对话，点上方「+ 新对话」开始</li>
          ) : (
            conversations.map((conv) => {
              const dt = conv.updated_at ? new Date(conv.updated_at) : null;
              return (
                <li
                  key={conv.id}
                  className={`conv-item${conv.id === currentId ? ' active' : ''}`}
                  onClick={() => onSelect(conv.id)}
                >
                  <div className="conv-title">{conv.title || '未命名对话'}</div>
                  <div className="conv-meta">
                    {conv.message_count || 0} 条 ·{' '}
                    {dt
                      ? dt.toLocaleString('zh-CN', { hour12: false }).slice(5)
                      : ''}
                  </div>
                  <div
                    className="conv-actions"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      title="重命名"
                      onClick={() => onRename(conv)}
                    >
                      ✎
                    </button>
                    <button
                      type="button"
                      title="删除会话"
                      onClick={() => onDelete(conv)}
                    >
                      ✕
                    </button>
                  </div>
                </li>
              );
            })
          )}
        </ul>
      </aside>
    </>
  );
}
