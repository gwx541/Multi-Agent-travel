const LS_CURRENT_CID = 'travelagent_current_cid';

export function getStoredConversationId(): string | null {
  return localStorage.getItem(LS_CURRENT_CID);
}

export function setStoredConversationId(id: string | null): void {
  if (id) localStorage.setItem(LS_CURRENT_CID, id);
  else localStorage.removeItem(LS_CURRENT_CID);
}

export function clearStoredConversationId(): void {
  localStorage.removeItem(LS_CURRENT_CID);
}
