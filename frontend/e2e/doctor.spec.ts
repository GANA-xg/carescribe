// Doctor full journey — login → patients → imaging → sepsis risk.

import { test, expect } from '@playwright/test';

test('doctor full journey', async ({ page }) => {
  // 1. Login with the seeded doctor account
  await page.goto('/auth/login');
  await page.getByLabel('Email').fill('doctor@example.com');
  await page.getByLabel('Password').fill('doctorpass123');
  await page.getByRole('button', { name: 'Sign in' }).click();

  // Redirects to the doctor dashboard with the patient list
  await expect(page).toHaveURL(/\/doctor$/);
  await expect(page.getByRole('searchbox')).toBeVisible();
  await expect(page.getByRole('list').first()).toBeVisible();

  // Grab a real patient id from the API (action links are desktop-only,
  // and this spec runs at mobile width).
  const token = await page.evaluate(() => localStorage.getItem('cs_token'));
  const res = await fetch('http://localhost:8000/patients', {
    headers: { Authorization: `Bearer ${token}` },
  });
  const { patients } = (await res.json()) as { patients: { id: string }[] };
  const patientId = patients[0]?.id ?? '00000000-0000-0000-0000-000000000000';
  // 2. Imaging page for a seeded patient — study list or empty state renders
  await page.goto(`/doctor/imaging/${patientId}`);
  await expect(page.getByRole('heading', { name: 'Imaging' })).toBeVisible();
  // Either studies render or the empty state does — both are valid.
  await expect(
    page.getByText(/No imaging studies|series/)
  ).toBeVisible();

  // 3. Sepsis risk: fill vitals → calculate → result card
  await page.goto(`/doctor/sepsis/${patientId ?? '00000000-0000-0000-0000-000000000000'}`);
  await page.getByLabel('Temperature').fill('38.5');
  await page.getByLabel('Heart Rate').fill('110');
  await page.getByLabel('Resp. Rate').fill('24');
  await page.getByLabel('WBC Count').fill('14');
  await page.getByLabel('Lactate Level').fill('3.2');
  await page.getByRole('button', { name: 'Calculate risk' }).click();

  // Result card with score + SHAP section
  await expect(page.getByRole('button', { name: 'Calculate risk' })).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByText("What's driving this score")).toBeVisible();
});
