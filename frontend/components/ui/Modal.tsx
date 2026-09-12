'use client';

import { forwardRef, useCallback, useEffect, useRef } from 'react';
import { cn } from '../../lib/utils';
import { X } from 'lucide-react';

export interface ModalProps {
  children: React.ReactNode;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
  title?: string;
  'aria-label'?: string;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

const Modal = forwardRef<HTMLDivElement, ModalProps>(
  ({ children, isOpen, onClose, className, title, 'aria-label': ariaLabel }, ref) => {
    const modalRef = useRef<HTMLDivElement>(null);

    const handleEscape = useCallback(
      (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
      },
      [onClose]
    );

    // Close on escape + trap focus inside modal
    useEffect(() => {
      if (!isOpen) return;

      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';

      const modal = modalRef.current;
      const previouslyFocused = document.activeElement as HTMLElement | null;

      const focusables = modal?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      const firstFocusable = focusables?.[0];
      const closeBtn = modal?.querySelector<HTMLButtonElement>('button[aria-label="Close modal"]');
      (closeBtn ?? firstFocusable)?.focus();

      const trapFocus = (e: KeyboardEvent) => {
        if (e.key !== 'Tab' || !modal) return;
        const focusableEls = Array.from(
          modal.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        ).filter((el) => el.offsetParent !== null);
        if (focusableEls.length === 0) return;
        const first = focusableEls[0];
        const last = focusableEls[focusableEls.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      };
      document.addEventListener('keydown', trapFocus);

      return () => {
        document.removeEventListener('keydown', handleEscape);
        document.removeEventListener('keydown', trapFocus);
        document.body.style.overflow = 'unset';
        previouslyFocused?.focus();
      };
    }, [isOpen, handleEscape]);

    if (!isOpen) return null;

    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-scrim)]"
        onClick={onClose}
      >
        <div
          ref={modalRef}
          role="dialog"
          aria-modal="true"
          aria-label={ariaLabel ?? title}
          className={cn(
            'relative mx-auto w-[calc(100%-32px)] max-w-[480px] rounded-[var(--rounded-md)] bg-white p-8',
            'shadow-card',
            className
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={onClose}
            className="absolute top-[var(--space-base)] right-[var(--space-base)] flex h-8 w-8 items-center justify-center rounded-full hover:bg-[var(--color-surface-soft)]"
            aria-label="Close modal"
          >
            <X className="h-4 w-4 text-[var(--color-muted)]" />
          </button>
          {title && (
            <h2 className="text-display-sm text-[var(--color-ink)] mb-[var(--space-base)] pr-8">
              {title}
            </h2>
          )}
          {children}
        </div>
      </div>
    );
  }
);

Modal.displayName = 'Modal';

export { Modal };
