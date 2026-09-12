'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, X } from 'lucide-react';
import { useAuthStore } from '../../store/auth';

type NavItem = { label: string; href: string };

const PATIENT_LINKS: NavItem[] = [
  { label: 'My Records', href: '/patient/passport' },
  { label: 'Prescriptions', href: '/patient' },
  { label: 'Chat', href: '/patient/chat' },
];

const DOCTOR_LINKS: NavItem[] = [
  { label: 'Patients', href: '/doctor' },
  { label: 'Imaging', href: '/doctor/imaging' },
  { label: 'Risk', href: '/doctor/sepsis' },
];

function initials(name: string | undefined): string {
  if (!name) return '··';
  return name
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

function useOutsideClick(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [onClose]);
  return ref;
}

export default function TopNav() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [avatarOpen, setAvatarOpen] = useState(false);

  const links = user?.role === 'doctor' ? DOCTOR_LINKS : PATIENT_LINKS;
  const avatarRef = useOutsideClick(() => setAvatarOpen(false));

  const isActive = (href: string) =>
    href === pathname || (href !== '/patient' && href !== '/doctor' && pathname.startsWith(href));

  const handleLogout = () => {
    logout();
    window.location.href = '/auth/login';
  };

  const navLink = (item: NavItem) => (
    <Link
      key={item.href}
      href={item.href}
      className={`text-nav pb-[var(--space-xs)] ${
        isActive(item.href)
          ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)]'
          : 'text-[var(--color-ink)] hover:text-[var(--color-primary)]'
      }`}
    >
      {item.label}
    </Link>
  );

  return (
    <header className="sticky top-0 z-40 h-20 bg-[var(--color-canvas)] border-b border-[var(--color-hairline)] px-6 min-[744px]:px-8">
      <div className="flex items-center justify-between h-full">
        {/* Wordmark */}
        <Link
          href={user?.role === 'doctor' ? '/doctor' : '/patient'}
          className="text-[700] 20px text-[var(--color-ink)] font-bold"
          style={{ fontSize: '20px' }}
          aria-label="CareScribe home"
        >
          CareScribe
        </Link>

        {/* Desktop nav */}
        <nav className="hidden min-[744px]:flex items-center gap-[var(--space-lg)]" aria-label="Main">
          {links.map(navLink)}
        </nav>

        {/* Desktop avatar */}
        <div className="hidden min-[744px]:relative min-[744px]:block" ref={avatarRef}>
          <button
            onClick={() => setAvatarOpen((v) => !v)}
            aria-label="Account menu"
            aria-expanded={avatarOpen}
            className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-surface-strong)] text-caption text-[var(--color-ink)] font-semibold"
          >
            {initials(user?.name)}
          </button>

          {avatarOpen && (
            <div className="absolute right-0 mt-[var(--space-sm)] w-48 rounded-[var(--rounded-md)] bg-white shadow-card p-[var(--space-sm)]">
              <p className="px-[var(--space-sm)] py-[var(--space-xxs)] text-caption-sm text-[var(--color-muted)] truncate">
                {user?.email}
              </p>
              <button
                onClick={() => {
                  setAvatarOpen(false);
                  window.location.href = '/patient/profile';
                }}
                className="w-full text-left px-[var(--space-sm)] py-[var(--space-sm)] rounded-[var(--rounded-sm)] text-body-sm text-[var(--color-ink)] hover:bg-[var(--color-surface-soft)]"
                aria-label="Profile"
              >
                Profile
              </button>
              <button
                onClick={() => {
                  setAvatarOpen(false);
                  window.location.href = '/patient/settings';
                }}
                className="w-full text-left px-[var(--space-sm)] py-[var(--space-sm)] rounded-[var(--rounded-sm)] text-body-sm text-[var(--color-ink)] hover:bg-[var(--color-surface-soft)]"
                aria-label="Settings"
              >
                Settings
              </button>
              <div className="my-[var(--space-xxs)] border-t border-[var(--color-hairline)]" />
              <button
                onClick={handleLogout}
                className="w-full text-left px-[var(--space-sm)] py-[var(--space-sm)] rounded-[var(--rounded-sm)] text-body-sm text-[var(--color-error)] hover:bg-[var(--color-surface-soft)]"
                aria-label="Sign out"
              >
                Sign out
              </button>
            </div>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          className="min-[744px]:hidden flex items-center justify-center"
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
        >
          <Menu className="h-6 w-6 text-[var(--color-ink)]" />
        </button>
      </div>

      {/* Mobile bottom sheet */}
      {menuOpen && (
        <div className="min-[744px]:hidden fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-[var(--color-scrim)]"
            onClick={() => setMenuOpen(false)}
            aria-hidden="true"
          />
          <div
            className="absolute bottom-0 left-0 right-0 bg-[var(--color-canvas)] rounded-t-[var(--rounded-lg)] pb-[var(--space-lg)] pt-[var(--space-base)] shadow-card"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation menu"
          >
            <div className="flex items-center justify-between px-[var(--space-base)] pb-[var(--space-sm)]">
              <span className="text-title-md text-[var(--color-ink)]">Menu</span>
              <button onClick={() => setMenuOpen(false)} aria-label="Close menu" className="p-[var(--space-xxs)]">
                <X className="h-6 w-6 text-[var(--color-ink)]" />
              </button>
            </div>
            {links.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className="flex h-14 items-center px-[var(--space-base)] text-nav text-[var(--color-ink)] hover:bg-[var(--color-surface-soft)]"
              >
                {item.label}
              </Link>
            ))}
            <div className="my-[var(--space-xs)] mx-[var(--space-base)] border-t border-[var(--color-hairline)]" />
            <button
              onClick={handleLogout}
              className="flex h-14 w-full items-center px-[var(--space-base)] text-nav text-[var(--color-error)]"
              aria-label="Sign out"
            >
              Sign out
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
