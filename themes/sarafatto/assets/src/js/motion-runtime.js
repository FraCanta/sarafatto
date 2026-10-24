import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

let connectedLenis = null;
let disconnectLenis = null;

/** Keep the shared ScrollTrigger instance synchronized with the page Lenis instance. */
export function connectLenisToScrollTrigger(lenis) {
  if (connectedLenis === lenis) return;

  disconnectLenis?.();
  disconnectLenis = null;
  connectedLenis = lenis;

  if (lenis) {
    disconnectLenis = lenis.on('scroll', ScrollTrigger.update);
  }
}

export { gsap, ScrollTrigger };
