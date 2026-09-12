// Chat history store — persists the conversation in Zustand so every
// assistant call can pass the full history array per the API contract.

import { create } from 'zustand';

export type StoredMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: string[];
  citations?: { source: string; text: string; similarity: number }[];
};

type ChatState = {
  messages: StoredMessage[];
  add: (message: Omit<StoredMessage, 'id'>) => void;
  clear: () => void;
};

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  add: (message) =>
    set((state) => ({
      messages: [...state.messages, { ...message, id: crypto.randomUUID() }],
    })),
  clear: () => set({ messages: [] }),
}));
