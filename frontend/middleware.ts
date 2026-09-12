// Role-based route protection for patient/doctor areas.
// The backend remains the security authority — this middleware only
// prevents obvious navigation mixups (doctor hitting /patient, etc).

import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

function roleFromToken(token: string | undefined): 'patient' | 'doctor' | null {
  if (!token) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const payload = JSON.parse(
      decodeURIComponent(
        atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
          .split('')
          .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      )
    );
    if (payload.role === 'doctor' || payload.role === 'patient') return payload.role;
    return null;
  } catch {
    return null;
  }
}

export function middleware(req: NextRequest) {
  const token =
    req.cookies.get('cs_token')?.value ??
    (req.headers.get('authorization')?.startsWith('Bearer ')
      ? req.headers.get('authorization')?.slice(7)
      : undefined);

  const role = roleFromToken(token);
  const { pathname } = req.nextUrl;

  const redirectTo = (path: string) => NextResponse.redirect(new URL(path, req.url));

  if (pathname.startsWith('/doctor') && role !== 'doctor') {
    // Doctors only; everyone else goes to sign-in.
    return redirectTo('/auth/login');
  }
  if (pathname.startsWith('/patient') && role === 'doctor') {
    return redirectTo('/doctor');
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/doctor/:path*', '/patient/:path*'],
};
