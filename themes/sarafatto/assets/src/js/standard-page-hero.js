import { gsap } from './motion-runtime.js';

const RESTING_CURVE = 'M0 0H1440V680 C1080 840 360 840 0 680Z';
const SCROLLED_CURVE = 'M0 0H1440V740 C1080 590 360 590 0 740Z';
const SETTLED_CURVE = 'M0 0H1440V740 C1080 625 360 625 0 740Z';

/** Animate shared internal-page heroes without affecting the Home or product detail pages. */
export function initStandardPageHeroes() {
  const heroes = Array.from(document.querySelectorAll('[data-standard-page-hero]'));
  if (!heroes.length || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;

  heroes.forEach((hero) => {
    const curve = hero.querySelector('[data-standard-page-hero-curve]');
    const content = hero.querySelector('[data-standard-page-hero-content]');
    if (!curve) return;

    gsap.set(curve, { attr: { d: RESTING_CURVE } });
    if (content) gsap.set(content, { y: 0 });

    const transition = gsap.timeline({
      scrollTrigger: {
        trigger: hero,
        start: 'top top',
        end: 'bottom top',
        scrub: 0.8,
        invalidateOnRefresh: true,
      },
    });

    if (content) {
      transition.to(content, {
        y: () => window.matchMedia('(max-width: 47.999rem)').matches ? -48 : -88,
        duration: 0.32,
        ease: 'none',
      }, 0);
    }

    transition.to(curve, { attr: { d: SCROLLED_CURVE }, duration: 0.52, ease: 'none' }, 0);
    transition.to(curve, { attr: { d: SETTLED_CURVE }, duration: 0.48, ease: 'none' }, 0.52);
  });

  return true;
}
