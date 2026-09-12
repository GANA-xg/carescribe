import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ChatPage from '../page';
import { useAuthStore } from '../../../../store/auth';
import { useChatStore } from '../../../../store/chat';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/patient/chat',
}));

const patient = {
  id: 'p1',
  name: 'Ananya Rao',
  email: 'patient@example.com',
  role: 'patient' as const,
};

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
  vi.stubGlobal('fetch', fn);
  return fn;
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: patient, hydrated: true });
  useChatStore.getState().clear();
});

describe('chat assistant', () => {
  it('shows the welcome bubble before any messages', () => {
    render(<ChatPage />);
    expect(screen.getByText(/Ask me anything about your health records/)).toBeInTheDocument();
  });

  it('sends a message and shows the reply with sources', async () => {
    mockFetch(200, {
      reply: 'You are on Paracetamol twice a day.',
      sources: ['prescription-2026-09-01'],
      citations: [],
    });
    render(<ChatPage />);
    const input = screen.getByLabelText('Message');
    fireEvent.change(input, { target: { value: 'What am I taking?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));

    expect(await screen.findByText('You are on Paracetamol twice a day.')).toBeInTheDocument();
    expect(screen.getByText('What am I taking?')).toBeInTheDocument();
    expect(screen.getByText('prescription-2026-09-01')).toBeInTheDocument();
  });

  it('sends full history with each chat request', async () => {
    const fn = mockFetch(200, { reply: 'first reply text', sources: [], citations: [] });
    render(<ChatPage />);
    const input = screen.getByLabelText('Message');

    fireEvent.change(input, { target: { value: 'first question' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await waitFor(() =>
      expect(useChatStore.getState().messages.some((m) => m.content === 'first reply text')).toBe(true)
    );

    fireEvent.change(input, { target: { value: 'second question' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await waitFor(() => expect(fn.mock.calls.length).toBe(2));

    const secondBody = JSON.parse(fn.mock.calls[1][1].body as string);
    expect(secondBody.patient_id).toBe('p1');
    expect(secondBody.message).toBe('second question');
    expect(secondBody.history).toEqual([
      { role: 'user', content: 'first question' },
      { role: 'assistant', content: 'first reply text' },
    ]);
  });

  it('shows a typing indicator while waiting', async () => {
    let resolveChat: (v: Response | PromiseLike<Response>) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            resolveChat = resolve;
          })
      )
    );
    render(<ChatPage />);
    const input = screen.getByLabelText('Message');
    fireEvent.change(input, { target: { value: 'hello' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    expect(screen.getByRole('status', { name: 'Assistant is typing' })).toBeInTheDocument();
    resolveChat({ ok: true, status: 200, json: () => Promise.resolve({ reply: 'hi', sources: [], citations: [] }) } as Response);
    await screen.findByText('hi');
    expect(screen.queryByRole('status', { name: 'Assistant is typing' })).not.toBeInTheDocument();
  });

  it('shows an inline error when the assistant fails', async () => {
    mockFetch(502, { detail: 'Assistant unavailable' });
    render(<ChatPage />);
    const input = screen.getByLabelText('Message');
    fireEvent.change(input, { target: { value: 'hello' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    expect(await screen.findByText(/Assistant unavailable/)).toBeInTheDocument();
  });

  it('clears the conversation via the clear button', async () => {
    mockFetch(200, { reply: 'ok', sources: [], citations: [] });
    render(<ChatPage />);
    const input = screen.getByLabelText('Message');
    fireEvent.change(input, { target: { value: 'hi' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }));
    await screen.findByText('ok');
    fireEvent.click(screen.getByRole('button', { name: 'Clear conversation' }));
    expect(screen.queryByText('ok')).not.toBeInTheDocument();
    expect(screen.getByText(/Ask me anything/)).toBeInTheDocument();
  });

  it('disables send until there is text', () => {
    render(<ChatPage />);
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
  });

  it('send button re-enables with text', () => {
    render(<ChatPage />);
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'hi' } });
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled();
  });
});
