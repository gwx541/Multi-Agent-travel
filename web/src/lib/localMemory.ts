/**
 * 本地记忆存储：所有记忆（长期偏好 + 全部会话历史）都保存在「手机本地」。
 *
 * - 原生 App：写入「所有文件访问」授权下的公共目录 `存储/TravelAgent/memory.json`，
 *   卸载 App 后文件仍保留；换机时把该文件拷到新机同名目录即可被读取。
 *   未授权时临时回退到 App 私有目录（卸载即删），授权后自动迁移。
 * - 浏览器（开发）：回退到 `localStorage`。
 *
 * 后端不再保存任何记忆：会话时由本模块把「偏好 + 近期上下文」随请求带给模型。
 */
import { Filesystem, Directory, Encoding } from '@capacitor/filesystem';
import { registerPlugin } from '@capacitor/core';
import { isNative } from './native';
import type { Conversation, Message } from '../types';

interface FileAccessPlugin {
  isGranted(): Promise<{ granted: boolean }>;
  requestAccess(): Promise<void>;
}

const FileAccess = registerPlugin<FileAccessPlugin>('FileAccess');

const DIR = 'TravelAgent';
const FILE = 'memory.json';
const REL_PATH = `${DIR}/${FILE}`;
const LS_KEY = 'travelagent_local_memory';
const MEMORY_VERSION = 1;

export interface LocalMsg {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
}

export interface LocalConv {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  archived?: boolean;
  messages: LocalMsg[];
}

export interface LocalMemory {
  version: number;
  nextMsgId: number;
  preferences: string[];
  conversations: LocalConv[];
}

let cache: LocalMemory | null = null;

function blank(): LocalMemory {
  return { version: MEMORY_VERSION, nextMsgId: 1, preferences: [], conversations: [] };
}

function nowIso(): string {
  return new Date().toISOString();
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `c-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalize(raw: unknown): LocalMemory {
  const mem = blank();
  if (!raw || typeof raw !== 'object') return mem;
  const obj = raw as Record<string, unknown>;
  if (Array.isArray(obj.preferences)) {
    mem.preferences = obj.preferences.filter(
      (p): p is string => typeof p === 'string' && p.trim().length > 0,
    );
  }
  if (Array.isArray(obj.conversations)) {
    mem.conversations = obj.conversations
      .filter((c): c is Record<string, unknown> => !!c && typeof c === 'object')
      .map((c) => ({
        id: String(c.id ?? uuid()),
        title: typeof c.title === 'string' ? c.title : '',
        createdAt: typeof c.createdAt === 'string' ? c.createdAt : nowIso(),
        updatedAt: typeof c.updatedAt === 'string' ? c.updatedAt : nowIso(),
        archived: !!c.archived,
        messages: Array.isArray(c.messages)
          ? c.messages
              .filter(
                (m): m is Record<string, unknown> => !!m && typeof m === 'object',
              )
              .map((m) => ({
                id: Number(m.id ?? 0),
                role: m.role === 'assistant' ? 'assistant' : 'user',
                content: typeof m.content === 'string' ? m.content : '',
                createdAt:
                  typeof m.createdAt === 'string' ? m.createdAt : nowIso(),
              }))
          : [],
      }));
  }
  const maxId = mem.conversations.reduce(
    (acc, c) => c.messages.reduce((a, m) => Math.max(a, m.id), acc),
    0,
  );
  mem.nextMsgId = Math.max(Number(obj.nextMsgId ?? 0) || 0, maxId + 1, 1);
  return mem;
}

// ---------- 底层读写（原生文件 / localStorage） ----------

async function externalGranted(): Promise<boolean> {
  if (!isNative()) return false;
  try {
    const r = await FileAccess.isGranted();
    return !!r.granted;
  } catch {
    return false;
  }
}

async function readRaw(): Promise<string | null> {
  if (!isNative()) {
    return localStorage.getItem(LS_KEY);
  }
  const granted = await externalGranted();
  const dirs = granted
    ? [Directory.ExternalStorage, Directory.Data]
    : [Directory.Data, Directory.ExternalStorage];
  for (const directory of dirs) {
    try {
      const r = await Filesystem.readFile({
        path: REL_PATH,
        directory,
        encoding: Encoding.UTF8,
      });
      if (typeof r.data === 'string' && r.data.trim()) return r.data;
    } catch {
      /* 文件不存在，尝试下一个目录 */
    }
  }
  return null;
}

async function writeRaw(text: string): Promise<void> {
  if (!isNative()) {
    localStorage.setItem(LS_KEY, text);
    return;
  }
  const directory = (await externalGranted())
    ? Directory.ExternalStorage
    : Directory.Data;
  try {
    await Filesystem.mkdir({ path: DIR, directory, recursive: true });
  } catch {
    /* 目录已存在 */
  }
  await Filesystem.writeFile({
    path: REL_PATH,
    directory,
    data: text,
    encoding: Encoding.UTF8,
    recursive: true,
  });
}

async function getMem(): Promise<LocalMemory> {
  if (cache) return cache;
  const raw = await readRaw();
  cache = raw ? normalize(JSON.parse(raw)) : blank();
  return cache;
}

async function persist(): Promise<void> {
  if (!cache) return;
  await writeRaw(JSON.stringify(cache));
}

function toConversation(c: LocalConv): Conversation {
  return {
    id: c.id,
    title: c.title,
    created_at: c.createdAt,
    updated_at: c.updatedAt,
    archived: !!c.archived,
    message_count: c.messages.length,
  };
}

function sortConvs(list: LocalConv[]): LocalConv[] {
  return [...list].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
}

// ---------- 公共 API（与原服务端 conversations API 形状对齐） ----------

export async function listConversations(): Promise<Conversation[]> {
  const mem = await getMem();
  return sortConvs(mem.conversations).map(toConversation);
}

export async function createConversation(title?: string): Promise<Conversation> {
  const mem = await getMem();
  const conv: LocalConv = {
    id: uuid(),
    title: title?.trim() || '',
    createdAt: nowIso(),
    updatedAt: nowIso(),
    archived: false,
    messages: [],
  };
  mem.conversations.unshift(conv);
  await persist();
  return toConversation(conv);
}

export async function updateConversation(
  id: string,
  patch: { title?: string; archived?: boolean },
): Promise<Conversation> {
  const mem = await getMem();
  const conv = mem.conversations.find((c) => c.id === id);
  if (!conv) throw new Error('会话不存在');
  if (patch.title !== undefined) conv.title = patch.title;
  if (patch.archived !== undefined) conv.archived = patch.archived;
  conv.updatedAt = nowIso();
  await persist();
  return toConversation(conv);
}

export async function deleteConversation(id: string): Promise<void> {
  const mem = await getMem();
  mem.conversations = mem.conversations.filter((c) => c.id !== id);
  await persist();
}

function latestConv(mem: LocalMemory): LocalConv | null {
  const active = mem.conversations.filter((c) => !c.archived);
  return sortConvs(active.length ? active : mem.conversations)[0] ?? null;
}

export async function listMessages(
  conversationId?: string | null,
): Promise<{ messages: Message[]; conversation_id?: string }> {
  const mem = await getMem();
  const conv = conversationId
    ? mem.conversations.find((c) => c.id === conversationId) ?? null
    : latestConv(mem);
  if (!conv) return { messages: [], conversation_id: undefined };
  return {
    conversation_id: conv.id,
    messages: conv.messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      created_at: m.createdAt,
    })),
  };
}

/** 追加一条消息；conversationId 为空时取最新会话，没有则新建。返回消息 id 与会话 id。 */
export async function appendMessage(
  conversationId: string | null | undefined,
  role: 'user' | 'assistant',
  content: string,
): Promise<{ id: number; conversationId: string }> {
  const mem = await getMem();
  let conv = conversationId
    ? mem.conversations.find((c) => c.id === conversationId) ?? null
    : latestConv(mem);
  if (!conv) {
    conv = {
      id: uuid(),
      title: '',
      createdAt: nowIso(),
      updatedAt: nowIso(),
      archived: false,
      messages: [],
    };
    mem.conversations.unshift(conv);
  }
  const id = mem.nextMsgId++;
  conv.messages.push({ id, role, content, createdAt: nowIso() });
  conv.updatedAt = nowIso();
  await persist();
  return { id, conversationId: conv.id };
}

export async function patchMessage(
  messageId: number,
  content: string,
): Promise<void> {
  const mem = await getMem();
  for (const c of mem.conversations) {
    const m = c.messages.find((x) => x.id === messageId);
    if (m) {
      m.content = content;
      c.updatedAt = nowIso();
      await persist();
      return;
    }
  }
}

/** 删除目标消息及其之后的所有消息（用于「编辑并重新生成」）。返回所在会话 id。 */
export async function truncateFrom(messageId: number): Promise<string | null> {
  const mem = await getMem();
  for (const c of mem.conversations) {
    const idx = c.messages.findIndex((x) => x.id === messageId);
    if (idx >= 0) {
      c.messages = c.messages.slice(0, idx);
      c.updatedAt = nowIso();
      await persist();
      return c.id;
    }
  }
  return null;
}

export async function getPreferences(): Promise<string[]> {
  const mem = await getMem();
  return [...mem.preferences];
}

export async function addPreferences(prefs: string[]): Promise<void> {
  const clean = prefs.map((p) => p.trim()).filter(Boolean);
  if (!clean.length) return;
  const mem = await getMem();
  let changed = false;
  for (const p of clean) {
    if (!mem.preferences.includes(p)) {
      mem.preferences.push(p);
      changed = true;
    }
  }
  if (changed) await persist();
}

export async function removePreference(pref: string): Promise<void> {
  const mem = await getMem();
  const before = mem.preferences.length;
  mem.preferences = mem.preferences.filter((p) => p !== pref);
  if (mem.preferences.length !== before) await persist();
}

/** 返回该会话最近 N 轮消息（升序），用作发给模型的上下文。 */
export async function recentHistory(
  conversationId: string | null | undefined,
  limit = 8,
): Promise<{ role: 'user' | 'assistant'; content: string }[]> {
  const mem = await getMem();
  const conv = conversationId
    ? mem.conversations.find((c) => c.id === conversationId) ?? null
    : latestConv(mem);
  if (!conv) return [];
  return conv.messages
    .slice(-limit)
    .map((m) => ({ role: m.role, content: m.content }));
}

// ---------- 存储授权（仅原生） ----------

export async function isPersistentStorageGranted(): Promise<boolean> {
  return externalGranted();
}

/** 打开系统「所有文件访问」授权页；用户授权后调用 migrateToExternalIfNeeded()。 */
export async function requestPersistentStorage(): Promise<void> {
  if (!isNative()) return;
  try {
    await FileAccess.requestAccess();
  } catch {
    /* ignore */
  }
}

/** 授权后把私有目录里的记忆迁移到公共目录（若公共目录尚无文件）。 */
export async function migrateToExternalIfNeeded(): Promise<void> {
  if (!isNative()) return;
  if (!(await externalGranted())) return;
  // 公共目录已有文件则不覆盖
  try {
    const ext = await Filesystem.readFile({
      path: REL_PATH,
      directory: Directory.ExternalStorage,
      encoding: Encoding.UTF8,
    });
    if (typeof ext.data === 'string' && ext.data.trim()) return;
  } catch {
    /* 公共目录暂无文件，继续迁移 */
  }
  // 强制重新从磁盘加载（此时 externalGranted=true，readRaw 会优先公共目录、回退私有目录）
  cache = null;
  const mem = await getMem();
  cache = mem;
  await persist();
}

export const MEMORY_FILE_HINT = `存储/${DIR}/${FILE}`;
