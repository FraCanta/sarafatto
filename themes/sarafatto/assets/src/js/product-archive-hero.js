import { gsap } from './motion-runtime.js';

const RESTING_CURVE = 'M0 0H1440V680 C1080 840 360 840 0 680Z';
const SCROLLED_CURVE = 'M0 0H1440V740 C1080 590 360 590 0 740Z';
const SETTLED_CURVE = 'M0 0H1440V740 C1080 625 360 625 0 740Z';

/** Give the products archive hero edge a restrained, reversible scroll response. */
export function initProductArchiveHero() {
  const hero = document.querySelector('.product-archive--products [data-product-archive-hero]');
  const curve = hero?.querySelector('[data-product-archive-curve]');
  if (!hero || !curve || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;

  // Fissa subito la forma concava iniziale prima che ScrollTrigger calcoli il progresso.
  gsap.set(curve, { attr: { d: RESTING_CURVE } });

  const transition = gsap.timeline({
    scrollTrigger: {
      trigger: hero,
      start: 'top top',
      end: 'bottom top',
      scrub: 0.8,
      invalidateOnRefresh: true,
    },
  });

  transition.to(curve, { attr: { d: SCROLLED_CURVE }, duration: 0.52, ease: 'none' }, 0);
  transition.to(curve, { attr: { d: SETTLED_CURVE }, duration: 0.48, ease: 'none' }, 0.52);

  return true;
}
