import { gsap } from './motion-runtime.js';

const HOME_REVEALS = [
  {
    section: '.home-worlds',
    groups: ['.home-worlds__intro'],
    items: ['.home-worlds__item'],
  },
  {
    section: '.home-personalized',
    groups: ['.home-personalized__content', '.home-personalized__footer'],
  },
  {
    section: '.home-choose-category',
    groups: ['.home-section-eyebrow', '.home-section-title'],
  },
  {
    section: '.home-featured',
    groups: ['.home-featured__intro'],
    items: ['.home-featured__list > *'],
  },
  {
    section: '.home-seasonal-feature',
    groups: ['.home-seasonal-feature__media', '.home-seasonal-feature__panel'],
  },
  {
    section: '.home-ideas',
    groups: ['.home-ideas__intro'],
    items: ['.home-ideas__item'],
  },
  {
    section: '.home-product-selection--new',
    groups: ['.home-product-selection__intro'],
    items: ['.home-product-selection .product-grid > *'],
  },
  {
    section: '.home-shipping-banner',
    groups: ['.home-shipping-banner__media', '.home-shipping-banner__content'],
  },
];

/** Reveal selected Home content as each piece enters the viewport. */
export function initHomeSectionReveals() {
  const home = document.querySelector('.site-main--home');

  if (!home || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return false;
  }

  const isMobile = window.matchMedia('(max-width: 47.999rem)').matches;

  HOME_REVEALS.forEach(({ section: sectionSelector, groups = [], items = [] }) => {
    const section = home.querySelector(sectionSelector);
    if (!section) return;

    const targets = [
      ...groups.flatMap((selector) => Array.from(section.querySelectorAll(selector))),
      ...items.flatMap((selector) => Array.from(section.querySelectorAll(selector))),
    ];

    targets.forEach((target) => {
      gsap.fromTo(target, {
        y: isMobile ? 48 : 72,
        scale: isMobile ? 0.97 : 0.94,
      }, {
        y: 0,
        scale: 1,
        duration: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: target,
          start: 'top bottom',
          end: 'top 58%',
          scrub: 0.4,
        },
      });
    });
  });

  const categoryItems = home.querySelectorAll('.home-choose-category__item');
  categoryItems.forEach((item) => {
    const verticalOffset = isMobile ? 72 : 96;

    gsap.fromTo(item, {
      y: verticalOffset,
      scale: isMobile ? 0.94 : 0.92,
    }, {
      y: 0,
      scale: 1,
      duration: 1,
      ease: 'none',
      scrollTrigger: {
        trigger: item,
        start: 'top 88%',
        end: 'top 55%',
        scrub: 0.55,
      },
    });
  });

  return true;
}
