import { gsap } from './motion-runtime.js';

/** Reveal the Home service links as they enter the viewport. */
export function initHomeServiceStrip() {
  const section = document.querySelector('.site-main--home .home-service-strip');
  const items = section?.querySelectorAll('.home-service-strip__item');

  if (!section || !items?.length || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return false;
  }

  const isMobile = window.matchMedia('(max-width: 47.999rem)').matches;

  gsap.fromTo(items, {
    y: isMobile ? 44 : 64,
    scale: isMobile ? 0.97 : 0.95,
  }, {
    y: 0,
    scale: 1,
    duration: 1,
    stagger: 0.14,
    ease: 'none',
    scrollTrigger: {
      trigger: section,
      start: 'top bottom',
      end: 'top 48%',
      scrub: 0.4,
    },
  });

  return true;
}
