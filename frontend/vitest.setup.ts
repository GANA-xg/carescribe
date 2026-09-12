import { expect } from 'vitest';
import '@testing-library/jest-dom/vitest';

export const test = expect;

// jsdom does not implement scrollIntoView
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}