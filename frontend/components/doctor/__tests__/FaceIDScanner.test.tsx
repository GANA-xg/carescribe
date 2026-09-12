import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FaceIDScanner from '../FaceIDScanner';
import { useAuthStore } from '../../../store/auth';

const doctor = {
  id: 'd1',
  name: 'Meera Kumar',
  email: 'doctor@example.com',
  role: 'doctor' as const,
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

// Minimal fake camera: a working getUserMedia + a real <video> that
// reports dimensions, plus canvas.captureStream-free toBlob stub.
function installFakeCamera() {
  const track = { stop: vi.fn() };
  const stream = { getTracks: () => [track] };
  vi.stubGlobal('navigator', {
    ...navigator,
    mediaDevices: { getUserMedia: () => Promise.resolve(stream) },
  });
  const realCreate = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
    if (tag === 'canvas') {
      return {
        width: 640,
        height: 640,
        getContext: () => ({ drawImage: vi.fn() }),
        toBlob: (cb: (b: Blob) => void) => cb(new Blob(['x'], { type: 'image/jpeg' })),
      } as unknown as HTMLCanvasElement;
    }
    return realCreate(tag);
  });
}

async function captureFrame() {
  fireEvent.click(screen.getByRole('button', { name: 'Start face scan' }));
  const video = (await screen.findByLabelText('Camera preview')) as HTMLVideoElement;
  video.play = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(video, 'videoWidth', { configurable: true, get: () => 640 });
  Object.defineProperty(video, 'videoHeight', { configurable: true, get: () => 640 });
  await waitFor(() => expect(video.srcObject).toBeTruthy());
  fireEvent.click(screen.getByRole('button', { name: 'Capture face photo' }));
}

beforeEach(() => {
  localStorage.clear();
  useAuthStore.setState({ user: doctor, hydrated: true });
  vi.restoreAllMocks();
});

describe('FaceIDScanner', () => {
  it('renders idle state with camera icon, scan button and always-visible name search', () => {
    render(<FaceIDScanner isOpen onClose={() => {}} onPatientSelected={() => {}} />);
    expect(screen.getByRole('button', { name: 'Start face scan' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Search by name instead' })).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
  });

  it('shows camera-denied error inline when getUserMedia fails', async () => {
    vi.stubGlobal('navigator', {
      ...navigator,
      mediaDevices: { getUserMedia: () => Promise.reject(new Error('denied')) },
    });
    render(<FaceIDScanner isOpen onClose={() => {}} onPatientSelected={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Start face scan' }));
    expect(await screen.findByText('Camera access was denied.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry face scan' })).toBeInTheDocument();
  });

  it('calls onPatientSelected with a name search', () => {
    const onSelected = vi.fn();
    render(<FaceIDScanner isOpen onClose={() => {}} onPatientSelected={onSelected} />);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Ananya Rao' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search by name instead' }));
    expect(onSelected).toHaveBeenCalledWith({ id: '', name: 'Ananya Rao' });
  });

  it('shows match result with name, confidence badge and actions', async () => {
    installFakeCamera();
    mockFetch(200, {
      patient_id: 'p1',
      name: 'Ananya Rao',
      confidence: 0.98,
      liveness_passed: true,
    });
    const onSelected = vi.fn();
    render(<FaceIDScanner isOpen onClose={() => {}} onPatientSelected={onSelected} />);

    await captureFrame();

    expect(await screen.findByText('Ananya Rao')).toBeInTheDocument();
    expect(screen.getByText('98% match')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open records' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Dismiss match' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open records' }));
    expect(onSelected).toHaveBeenCalledWith({ id: 'p1', name: 'Ananya Rao' });
  });

  it('shows the name input immediately on no-match', async () => {
    installFakeCamera();
    mockFetch(200, {
      patient_id: null,
      name: null,
      confidence: 0.2,
      liveness_passed: true,
    });
    render(<FaceIDScanner isOpen onClose={() => {}} onPatientSelected={() => {}} />);

    await captureFrame();

    expect(await screen.findByText('No match found')).toBeInTheDocument();
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Search by name' })).toBeInTheDocument();
  });

  it('shows liveness failure message with try again', async () => {
    installFakeCamera();
    mockFetch(200, {
      patient_id: null,
      name: null,
      confidence: 0,
      liveness_passed: false,
    });
    render(<FaceIDScanner isOpen onClose={() => {}} onPatientSelected={() => {}} />);

    await captureFrame();

    expect(await screen.findByText('Please face the camera directly.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try face scan again' })).toBeInTheDocument();
  });
});
