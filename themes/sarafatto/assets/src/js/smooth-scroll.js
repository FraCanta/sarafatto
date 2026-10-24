import Lenis from 'lenis';
import 'lenis/dist/lenis.css';
import { setLenisInstance } from './scroll-bridge.js';

let lenisInstance = null;

export function initSmoothScroll() {
  if (typeof window === 'undefined') return null;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return null;
  if (lenisInstance) return lenisInstance;

  lenisInstance = new Lenis({
    autoRaf: true,
    smoothWheel: true,
    syncTouch: false,
    lerp: 0.1,
    anchors: true,
    stopInertiaOnNavigate: true,
  });
  setLenisInstance(lenisInstance);

  return lenisInstance;
}
