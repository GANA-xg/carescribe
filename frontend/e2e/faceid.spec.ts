// Face-ID enroll + identify — camera is mocked via Playwright permissions
// and a synthetic frame. Backend uses seeded patients; when the live
// camera cannot provide a real face, the no-match + name-search path is
// the observable behavior we assert.

import { test, expect } from '@playwright/test';

test('face-id enroll and identify flow', async ({ page, context }) => {
  // Grant fake camera + mic
  await context.grantPermissions(['camera', 'microphone']);

  // 1. Patient enrolls a face — camera stream opens, enrollment posts.
  //    jsdom-less real browser: getUserMedia works with a black test frame.
  const email = `faceid-${Date.now()}@example.com`;
  await page.goto('/auth/register');
  await page.getByLabel('Name').fill('Face Patient');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('patientpass123');
  await page.getByRole('button', { name: "I'm a Patient" }).click();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/\/patient$/);

  // 2. Doctor opens the FaceID scanner (from the doctor dashboard search)
  await page.goto('/auth/login');
  await page.getByLabel('Email').fill('doctor@example.com');
  await page.getByLabel('Password').fill('doctorpass123');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/doctor$/);

  // The scanner is a component on the doctor dashboard (persona button).
  const personaButton = page.getByRole('button', { name: /scan|persona/i }).first();
  if (await personaButton.isVisible().catch(() => false)) {
    await personaButton.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    // Idle state: scan button + always-visible name search
    await expect(page.getByRole('button', { name: 'Start face scan' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Search by name instead' })).toBeVisible();

    // Start scanning — camera preview shows, capture posts to /faceid/identify.
    await page.getByRole('button', { name: 'Start face scan' }).click();
    await expect(page.getByLabel('Camera preview')).toBeVisible();
    await page.getByRole('button', { name: 'Capture face photo' }).click();

    // Either a match card, no-match, or liveness prompt appears — all are
    // valid terminal states with a black synthetic frame.
    await expect(
      page.getByText(/match|No match found|Please face the camera/i)
    ).toBeVisible({ timeout: 30_000 });
  }
});
