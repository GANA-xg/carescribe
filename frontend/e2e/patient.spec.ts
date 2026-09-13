// Patient full journey — register → upload → passport → drugs.
// Runs against the real backend (localhost:8000) via the Next dev server.

import { test, expect } from '@playwright/test';

const unique = () => `e2e-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

test('patient full journey', async ({ page }) => {
  const email = `${unique()}@example.com`;

  // 1. Register as a new patient
  await page.goto('/auth/register');
  await page.getByLabel('Name').fill('E2E Patient');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('patientpass123');
  await page.getByRole('button', { name: "I'm a Patient" }).click();
  await page.getByRole('button', { name: 'Create account' }).click();

  // Redirects to the patient dashboard
  await expect(page).toHaveURL(/\/patient$/);
  await expect(page.getByText(/Good (morning|afternoon|evening), E2E/)).toBeVisible();
  await expect(page.getByText('No prescriptions yet')).toBeVisible();

  // 2. Upload a prescription image
  await page.goto('/patient/upload');
  await expect(page.getByText('Capture')).toBeVisible();
  await expect(page.getByText('Processing')).toBeVisible();
  await expect(page.getByText('Review')).toBeVisible();

  // Hidden file input inside the capture zone
  await page.setInputFiles(
    'input[type="file"][accept="image/*"]',
    'e2e/fixtures/sample-prescription.png'
  );

  await expect(page.getByAltText('Prescription preview')).toBeVisible();
  await page.getByRole('button', { name: 'Use this photo' }).click();
  await expect(page.getByText('Reading your prescription…')).toBeVisible();

  // OCR polling → review step (backend + models service do the work).
  // In core mode the regex NER fallback may not extract drugs from the
  // test image, so the review UI is exercised by adding one manually.
  const diagnosisField = page.getByLabel('Diagnosis');
  await expect(diagnosisField).toBeVisible({ timeout: 60_000 });

  const addDrug = page.getByLabel('Add a drug');
  await addDrug.fill('Paracetamol');
  await page.getByRole('button', { name: 'Add drug' }).click();
  await expect(page.getByText('Paracetamol')).toBeVisible();

  await page.getByRole('button', { name: 'Save to Health Passport' }).click();
  await expect(page.getByText('Saved ✓')).toBeVisible();

  // 3. Passport shows the record in the timeline
  await page.goto('/patient/passport');
  await expect(page.getByRole('tab', { name: 'Prescriptions' })).toBeVisible();
  await expect(page.getByRole('listitem').first()).toBeVisible();

  // 4. Drug comparison page renders a generic alternative
  await page.goto('/patient/drugs?drugs=Paracetamol');
  await expect(page.getByText('Generic Alternatives')).toBeVisible();
  await expect(page.getByText('Paracetamol', { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Save ₹/)).toBeVisible();
});
