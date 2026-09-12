import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ImagingPage from '../page';
import { useAuthStore } from '../../../../../store/auth';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/doctor/imaging',
}));

function renderImaging(patientId = 'p1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ImagingPage params={{ patient_id: patientId }} />
    </QueryClientProvider>
  );
}

const doctor = {
  id: 'd1',
  name: 'Meera Kumar',
  email: 'doctor@example.com',
  role: 'doctor' as const,
};

const studiesBody = {
  studies: [
    {
      study_instance_uid: '1.2.840.1',
      orthanc_study_id: 'os-1',
      date: '20260901',
      description: 'Brain MRI',
      series_count: 3,
      ohif_url: '/viewer?StudyInstanceUIDs=1.2.840.1',
    },
    {
      study_instance_uid: '1.2.840.2',
      orthanc_study_id: 'os-2',
      date: '20260815',
      description: 'Head CT',
      series_count: 1,
      ohif_url: '/viewer?StudyInstanceUIDs=1.2.840.2',
    },
  ],
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
  useAuthStore.setState({ user: doctor, hydrated: true });
});

describe('imaging page', () => {
  it('renders the title', async () => {
    mockFetch(200, studiesBody);
    renderImaging();
    expect(await screen.findByRole('heading', { name: 'Imaging', level: 1 })).toBeInTheDocument();
  });

  it('lists studies with description, date and series count', async () => {
    mockFetch(200, studiesBody);
    renderImaging();
    expect(await screen.findByText('Brain MRI')).toBeInTheDocument();
    expect(screen.getByText('Head CT')).toBeInTheDocument();
    expect(screen.getAllByText(/series/).length).toBe(2);
  });

  it('shows empty state when there are no studies', async () => {
    mockFetch(200, { studies: [] });
    renderImaging();
    expect(
      await screen.findByText('No imaging studies for this patient yet.')
    ).toBeInTheDocument();
  });

  it('shows an error state when loading fails', async () => {
    mockFetch(500, { detail: 'Orthanc down' });
    renderImaging();
    expect(await screen.findByText("Couldn't load studies. Please refresh.")).toBeInTheDocument();
  });

  it('loads the OHIF iframe on :3001 when a study is selected', async () => {
    mockFetch(200, studiesBody);
    renderImaging();
    fireEvent.click(await screen.findByRole('button', { name: /Open study Brain MRI/ }));
    const iframe = screen.getByTitle('OHIF viewer for Brain MRI');
    expect(iframe).toHaveAttribute('src', 'http://localhost:3001/viewer?StudyInstanceUIDs=1.2.840.1');
  });

  it('shows the tumor AI card with disclaimer once a study is selected', async () => {
    mockFetch(200, studiesBody);
    renderImaging();
    expect(screen.queryByRole('heading', { name: '🧠 Tumor AI' })).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: /Open study Brain MRI/ }));
    expect(screen.getByRole('heading', { name: '🧠 Tumor AI', level: 2 })).toBeInTheDocument();
    expect(
      screen.getByText('⚠️ AI result is for clinical reference only — not a diagnosis.')
    ).toBeInTheDocument();
  });

  it('runs tumor analysis and shows prediction + confidence bar', async () => {
    let calls = 0;
    const fn = vi.fn().mockImplementation(() => {
      calls++;
      const body =
        calls === 1
          ? studiesBody
          : { prediction: 'glioma', confidence: 0.87, heatmap_url: null, probabilities: null };
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
    });
    vi.stubGlobal('fetch', fn);

    renderImaging();
    fireEvent.click(await screen.findByRole('button', { name: /Open study Brain MRI/ }));

    const file = new File(['dicom'], 'scan.dcm', { type: 'application/dicom' });
    const input = screen.getByLabelText('DICOM file for AI analysis') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText('glioma')).toBeInTheDocument();
    const bar = screen.getByRole('progressbar', { name: 'AI confidence' });
    expect(bar).toHaveAttribute('aria-valuenow', '87');
  });
});
