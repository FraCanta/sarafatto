import './app.js';

import { getLenisInstance } from './scroll-bridge.js';
import { connectLenisToScrollTrigger, gsap, ScrollTrigger } from './motion-runtime.js';
import { initContactScrollRibbon } from './home-scroll-ribbon.js';

const RESTING_CURVE = 'M0 0H1440V680 C1080 840 360 840 0 680Z';
const SCROLLED_CURVE = 'M0 0H1440V740 C1080 590 360 590 0 740Z';
const SETTLED_CURVE = 'M0 0H1440V740 C1080 625 360 625 0 740Z';

/** Animate the Contact hero curve and the map framing independently on scroll. */
function initContactMotion() {
  const page = document.querySelector('.contact-page');
  const hero = page?.querySelector('[data-contact-hero]');
  const curve = hero?.querySelector('[data-contact-curve]');
  const content = hero?.querySelector('.contact-page__hero-content');
  const mapFrame = page?.querySelector('[data-contact-map-frame]');

  if (!page || !hero || !curve || !mapFrame) return false;

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return false;
  }

  gsap.set(curve, { attr: { d: RESTING_CURVE } });
  if (content) gsap.set(content, { y: 0 });

  const heroTimeline = gsap.timeline({
    scrollTrigger: {
      trigger: hero,
      start: 'top top',
      end: 'bottom 20%',
      scrub: 0.9,
      invalidateOnRefresh: true,
    },
  });

  if (content) {
    heroTimeline.to(content, {
      y: () => window.matchMedia('(max-width: 47.999rem)').matches ? -48 : -88,
      duration: 0.32,
      ease: 'none',
    }, 0);
  }

  heroTimeline.to(curve, { attr: { d: SCROLLED_CURVE }, duration: 0.58, ease: 'none' }, 0);
  heroTimeline.to(curve, { attr: { d: SETTLED_CURVE }, duration: 0.42, ease: 'none' }, 0.58);

  gsap.fromTo(mapFrame, {
    clipPath: 'inset(0% 0% round 0px)',
  }, {
    clipPath: () => {
      const mobile = window.matchMedia('(max-width: 47.999rem)').matches;
      const targetWidth = Math.min(window.innerWidth * (mobile ? 0.94 : 0.9), 1300);
      const sideInset = ((window.innerWidth - targetWidth) / (2 * window.innerWidth)) * 100;
      const radius = mobile ? 20 : 32;
      return `inset(0% ${sideInset}% round ${radius}px)`;
    },
    ease: 'none',
    scrollTrigger: {
      trigger: hero,
      start: 'top top',
      end: 'bottom top',
      scrub: 0.8,
      invalidateOnRefresh: true,
    },
  });

  window.addEventListener('load', () => ScrollTrigger.refresh(), { once: true });
  return true;
}

connectLenisToScrollTrigger(getLenisInstance());
initContactMotion();
initContactScrollRibbon();

const status = document.querySelector('[data-contact-status]');
if (status) {
  window.requestAnimationFrame(() => status.focus({ preventScroll: true }));
}
