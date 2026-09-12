'use client';

import { useEffect, useRef, useState } from 'react';
import { Mic, Send } from 'lucide-react';
import AuthenticatedShell from '../../../components/shared/AuthenticatedShell';
import { api } from '../../../lib/api';
import { useAuthStore } from '../../../store/auth';
import { useChatStore, type StoredMessage } from '../../../store/chat';
import type { ChatMessage } from '../../../lib/types';

function TypingDots() {
  return (
    <div className="flex gap-[6px]" role="status" aria-label="Assistant is typing">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="typing-dot h-2 w-2 rounded-full bg-[var(--color-muted)] inline-block"
        />
      ))}
    </div>
  );
}

function AssistantBubble({ message }: { message: StoredMessage }) {
  return (
    <div className="self-start bg-white shadow-card rounded-[var(--rounded-md)] px-[16px] py-[12px] max-w-sm">
      <p className="text-body-sm text-[var(--color-ink)] whitespace-pre-wrap">{message.content}</p>
      {message.sources && message.sources.length > 0 && (
        <div className="flex flex-wrap gap-[var(--space-xxs)] mt-[var(--space-sm)]">
          {message.sources.map((source, i) => (
            <span
              key={`${source}-${i}`}
              className="rounded-full bg-[var(--color-surface-strong)] px-[8px] py-[2px] text-[11px] text-[var(--color-muted)]"
            >
              {source}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function UserBubble({ message }: { message: StoredMessage }) {
  return (
    <div className="self-end bg-[var(--color-primary)] text-white rounded-[var(--rounded-md)] px-[16px] py-[12px] max-w-xs">
      <p className="text-body-sm whitespace-pre-wrap">{message.content}</p>
    </div>
  );
}

function ChatBody() {
  const user = useAuthStore((s) => s.user)!;
  const messages = useChatStore((s) => s.messages);
  const addMessage = useChatStore((s) => s.add);
  const clear = useChatStore((s) => s.clear);

  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, sending]);

  // Always read fresh store state — a closure over `messages` goes stale
  // between the local addMessage and the request build.
  const historyBefore = (excludeLast: boolean): ChatMessage[] => {
    const all = useChatStore
      .getState()
      .messages.slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));
    return excludeLast ? all.slice(0, -1) : all;
  };

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || sending) return;
    setDraft('');
    setError(null);
    addMessage({ role: 'user', content });
    setSending(true);
    try {
      const res = await api.assistant.chat({
        patient_id: user.id,
        message: content,
        history: historyBefore(true),
      });
      addMessage({ role: 'assistant', content: res.reply, sources: res.sources });
    } catch (e) {
      setError(
        e instanceof Error && e.message ? e.message : 'The assistant is unavailable right now.'
      );
    } finally {
      setSending(false);
    }
  };

  const startRecording = async () => {
    setMicError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setSending(true);
        try {
          const res = await api.assistant.voice(blob, user.id);
          if (res.transcript) addMessage({ role: 'user', content: `🎙️ ${res.transcript}` });
          addMessage({ role: 'assistant', content: res.reply, sources: res.sources });
        } catch (e) {
          setError(
            e instanceof Error && e.message ? e.message : 'Voice message failed.'
          );
        } finally {
          setSending(false);
        }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setRecording(true);
    } catch {
      setMicError('Microphone access was denied.');
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setRecording(false);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-80px)]">
      <div className="flex items-center justify-between px-0 py-[var(--space-base)]">
        <h1 className="text-[20px] font-bold text-[var(--color-ink)]">Chat Assistant</h1>
        {messages.length > 0 && (
          <button
            onClick={clear}
            className="text-caption-sm text-[var(--color-muted)] hover:text-[var(--color-ink)]"
            aria-label="Clear conversation"
          >
            Clear chat
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-0 py-[var(--space-base)] flex flex-col gap-[var(--space-base)]">
        {messages.length === 0 && !sending && (
          <div className="self-start bg-white shadow-card rounded-[var(--rounded-md)] px-[16px] py-[12px] max-w-sm">
            <p className="text-body-sm text-[var(--color-ink)]">
              Hi {user.name.split(/\s+/)[0]}! Ask me anything about your health records —
              prescriptions, diagnoses, or visits.
            </p>
          </div>
        )}
        {messages.map((m) =>
          m.role === 'user' ? <UserBubble key={m.id} message={m} /> : <AssistantBubble key={m.id} message={m} />
        )}
        {sending && <TypingDots />}
        <div ref={bottomRef} />
      </div>

      {(error || micError) && (
        <p role="alert" className="text-body-sm text-[var(--color-error)] pb-[var(--space-sm)]">
          {error ?? micError}
        </p>
      )}

      {/* Input bar */}
      <div className="flex-none border-t border-[var(--color-hairline)] py-[12px]">
        <div className="flex items-center gap-[var(--space-sm)]">
          <button
            onClick={recording ? stopRecording : startRecording}
            aria-label={recording ? 'Stop recording' : 'Start voice message'}
            className={`flex h-10 w-10 flex-none items-center justify-center rounded-full ${
              recording
                ? 'bg-[var(--color-primary)] text-white'
                : 'bg-[var(--color-surface-strong)] text-[var(--color-ink)]'
            }`}
          >
            <Mic className="h-5 w-5" />
          </button>

          <input
            aria-label="Message"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void send(draft);
              }
            }}
            placeholder="Ask about your records…"
            className="flex-1 h-10 rounded-full border border-[var(--color-hairline)] px-[16px] text-body-sm text-[var(--color-ink)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)]"
          />

          <button
            onClick={() => void send(draft)}
            disabled={!draft.trim() || sending}
            aria-label="Send message"
            className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-[var(--color-primary)] text-white disabled:opacity-40"
          >
            <Send className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <AuthenticatedShell>
      <ChatBody />
    </AuthenticatedShell>
  );
}
