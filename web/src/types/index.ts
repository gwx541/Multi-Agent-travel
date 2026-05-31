export interface User {
  id: string;
  email: string;
}

export interface ChatLocation {
  lng: number;
  lat: number;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  archived: boolean;
  message_count: number;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at?: string;
}

export interface Poi {
  name: string;
  location?: string;
  address?: string;
}

export interface FinalPayload {
  text: string;
  pois?: Poi[];
  location?: ChatLocation;
  location_info?: Record<string, string>;
  conversation_id?: string;
  conversation_title?: string;
  message_ids?: { user?: number; assistant?: number };
  new_preferences?: string[];
}

export type ChatSSEEventType =
  | 'manager'
  | 'agent_start'
  | 'agent_end'
  | 'final'
  | 'error';

export interface AppConfig {
  amap_js_key?: string;
  amap_js_security?: string;
  auth_required: boolean;
}

export interface ChatMessage {
  id?: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  html?: string;
  agentName?: string;
}

export interface LocationInfo {
  city?: string;
  district?: string;
  township?: string;
  street?: string;
  province?: string;
  address?: string;
}

export interface LocateResult extends LocationInfo {
  lng: number;
  lat: number;
  source?: string;
  approximate?: boolean;
}
